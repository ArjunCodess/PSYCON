#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <NimBLEDevice.h>
#include <Preferences.h>
#include <WiFi.h>
#include "driver/i2s.h"
#include "esp_timer.h"

static const int I2S_WS_PIN = 25;
static const int I2S_SCK_PIN = 26;
static const int I2S_SD_PIN = 33;
static constexpr size_t SAMPLES = 8000;
struct __attribute__((packed)) Packet {
  char magic[4]; uint8_t version, headerLength, stream, flags;
  uint32_t deviceId, sequence; uint64_t timestampUs;
  uint32_t sampleCount, samplePeriodUs, payloadLength, crc;
  int16_t samples[SAMPLES];
};
static_assert(offsetof(Packet, samples) == 40, "Protocol v2 header length");
QueueHandle_t packets;
Preferences preferences;
NimBLECharacteristic *statusCharacteristic;
String ssid, password, apiUrl, token, sessionId;
uint32_t deviceId, nextSequence, reservedEnd;
volatile bool paused = true, provisioning = false, rebootRequested = false;
volatile bool serverRejected = false;
volatile uint32_t droppedSamples = 0;
portMUX_TYPE stateMutex = portMUX_INITIALIZER_UNLOCKED;

uint32_t crcUpdate(uint32_t crc, const uint8_t *data, size_t length) {
  for (size_t i=0;i<length;++i) { crc^=data[i]; for (uint8_t b=0;b<8;++b) crc=(crc>>1)^((crc&1)?0xedb88320U:0U); }
  return crc;
}
uint32_t allocateSequence() {
  if (nextSequence >= reservedEnd) {
    if (nextSequence > UINT32_MAX-1024) { paused=true; return UINT32_MAX; }
    const uint32_t end=nextSequence+1024;
    // Stop capture if durable reservation fails; never publish a sequence that can be reused.
    if (preferences.putUInt("reserved",end)!=sizeof(uint32_t)) { paused=true; return UINT32_MAX; }
    reservedEnd=end;
  }
  return nextSequence++;
}
void captureTask(void *) {
  Packet packet{}; memcpy(packet.magic,"PSY2",4);
  packet.version=2; packet.headerLength=40; packet.stream=1; packet.deviceId=deviceId;
  packet.sampleCount=SAMPLES; packet.samplePeriodUs=62; packet.payloadLength=SAMPLES*2;
  int32_t dma[256]; size_t count=0; uint64_t nextStart=0; bool wasPaused=true;
  while (true) {
    size_t bytes=0;
    const auto result=i2s_read(I2S_NUM_0,dma,sizeof(dma),&bytes,pdMS_TO_TICKS(100));
    // Drain DMA while paused so resuming cannot publish old private speech.
    if (paused) { count=0; wasPaused=true; continue; }
    if (wasPaused) { nextStart=esp_timer_get_time()-(bytes/4)*1000000ULL/16000; wasPaused=false; }
    if (result!=ESP_OK || !bytes) {
      portENTER_CRITICAL(&stateMutex); droppedSamples+=count; portEXIT_CRITICAL(&stateMutex);
      count=0; wasPaused=true; continue;
    }
    for (size_t i=0;i<bytes/4;++i) {
      if (!count) packet.timestampUs=nextStart;
      packet.samples[count++]=static_cast<int16_t>(dma[i]>>16);
      if (count==SAMPLES) {
        packet.sequence=allocateSequence();
        uint32_t crc=crcUpdate(0xffffffffU,reinterpret_cast<uint8_t *>(&packet),36);
        packet.crc=crcUpdate(crc,reinterpret_cast<uint8_t *>(packet.samples),packet.payloadLength)^0xffffffffU;
        if (packet.sequence==UINT32_MAX || xQueueSend(packets,&packet,0)!=pdTRUE) {
          portENTER_CRITICAL(&stateMutex); droppedSamples+=SAMPLES; portEXIT_CRITICAL(&stateMutex);
        }
        nextStart+=SAMPLES*1000000ULL/16000; count=0;
      }
    }
  }
}
int post(const String &path,const uint8_t *data,size_t size,const char *type) {
  WiFiClient client; HTTPClient http; http.setConnectTimeout(3000); http.setTimeout(3000);
  if (!http.begin(client,apiUrl+path)) return -1;
  http.addHeader("Authorization","Bearer "+token); http.addHeader("Content-Type",type);
  int code=http.POST(const_cast<uint8_t *>(data),size); http.end(); return code;
}
bool sendStatus(const char *event,uint32_t lost=0) {
  JsonDocument json; json["device_id"]=deviceId; json["event_type"]=event;
  json["device_timestamp_us"]=static_cast<uint64_t>(esp_timer_get_time());
  json["payload"]["paused"]=paused; json["payload"]["dropped_samples"]=lost;
  String body; serializeJson(json,body);
  int code=post("/sessions/"+sessionId+"/status",reinterpret_cast<const uint8_t *>(body.c_str()),body.length(),"application/json");
  return code>=200 && code<300;
}
void syncClock() {
  WiFiClient client; HTTPClient http; http.setTimeout(3000);
  if (!http.begin(client,apiUrl+"/time")) return;
  if (http.GET()!=200) { http.end(); return; }
  uint64_t received=esp_timer_get_time(); JsonDocument time;
  auto failed=deserializeJson(time,http.getString()); http.end(); if (failed) return;
  JsonDocument clock; clock["device_id"]=deviceId;
  clock["t0_backend_us"]=time["backend_time_us"].as<uint64_t>(); clock["t1_device_us"]=received;
  clock["t2_device_us"]=static_cast<uint64_t>(esp_timer_get_time());
  String body; serializeJson(clock,body);
  post("/sessions/"+sessionId+"/clock-sync",reinterpret_cast<const uint8_t *>(body.c_str()),body.length(),"application/json");
}
void networkTask(void *) {
  Packet packet; bool pending=false, connected=false; uint32_t lastSync=0,lastStatus=0,lastReconnect=0;
  while (true) {
    if (ssid.isEmpty() || token.isEmpty() || sessionId.isEmpty()) { vTaskDelay(pdMS_TO_TICKS(1000)); continue; }
    if (WiFi.status()!=WL_CONNECTED) {
      connected=false;
      if (millis()-lastReconnect>10000) { WiFi.begin(ssid.c_str(),password.c_str()); lastReconnect=millis(); }
      vTaskDelay(pdMS_TO_TICKS(1000)); continue;
    }
    if (!connected) { sendStatus("reconnect"); syncClock(); connected=true; }
    if (millis()-lastSync>30000) { syncClock(); lastSync=millis(); }
    if (millis()-lastStatus>10000) { sendStatus("heartbeat"); lastStatus=millis(); }
    uint32_t lost; portENTER_CRITICAL(&stateMutex); lost=droppedSamples; portEXIT_CRITICAL(&stateMutex);
    if (lost && sendStatus("overrun",lost)) { portENTER_CRITICAL(&stateMutex); droppedSamples-=lost; portEXIT_CRITICAL(&stateMutex); }
    if (serverRejected) { vTaskDelay(pdMS_TO_TICKS(1000)); continue; }
    if (!pending) pending=xQueueReceive(packets,&packet,pdMS_TO_TICKS(100))==pdTRUE;
    if (!pending) continue;
    int code=post("/sessions/"+sessionId+"/chunks",reinterpret_cast<uint8_t *>(&packet),sizeof(packet),"application/vnd.psycon.chunk-v2");
    if (code>=200 && code<300) pending=false; // Retry exact bytes until acknowledged, including idempotent replies.
    else if (code>=400 && code<500 && code!=429 && code!=408) { paused=true; serverRejected=true; statusCharacteristic->setValue("paused: server rejected chunk"); }
    vTaskDelay(pdMS_TO_TICKS(100));
  }
}
bool privateApiUrl(const String &url) {
  if (!url.startsWith("http://")) return false;
  const int slash=url.indexOf('/',7);
  if (slash<0 || url.substring(slash)!="/api/v1") return false;
  String authority=url.substring(7,slash);
  const int colon=authority.indexOf(':');
  if (colon>=0) {
    const String port=authority.substring(colon+1);
    if (port.isEmpty()) return false;
    for (size_t i=0;i<port.length();++i) if (!isDigit(port[i])) return false;
    if (port.toInt()<1 || port.toInt()>65535) return false;
    authority=authority.substring(0,colon);
  }
  IPAddress address;
  if (!address.fromString(authority)) return false;
  return address[0]==10 || (address[0]==192 && address[1]==168) ||
    (address[0]==172 && address[1]>=16 && address[1]<=31);
}
class Controls : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic *characteristic,NimBLEConnInfo &info) override {
    if (!info.isEncrypted() || !info.isAuthenticated()) return;
    std::string input=characteristic->getValue();
    if (input=="pause") { paused=true; return; }
    if (input=="resume" && !token.isEmpty() && !provisioning) { serverRejected=false; paused=false; return; }
    if (!provisioning || input.size()>1800) return;
    JsonDocument config; if (deserializeJson(config,input)) return;
    String url=config["api_url"] | ""; String session=config["session_id"] | ""; String credential=config["token"] | "";
    // Initial hardware pilot uses only a private LAN, never plaintext public transport.
    if (!privateApiUrl(url)) return;
    if (session.length()!=36 || credential.length()<32 || !config["device_id"].is<uint32_t>()) return;
    preferences.putString("ssid",config["ssid"] | ""); preferences.putString("password",config["password"] | "");
    preferences.putString("api",url); preferences.putString("session",session); preferences.putString("token",credential);
    uint32_t newId=config["device_id"].as<uint32_t>();
    preferences.putUInt("device",newId); rebootRequested=true;
  }
};
void setup() {
  Serial.begin(115200); pinMode(0,INPUT_PULLUP); provisioning=digitalRead(0)==LOW;
  preferences.begin("psycon-ear",false);
  ssid=preferences.getString("ssid",""); password=preferences.getString("password","");
  apiUrl=preferences.getString("api",""); token=preferences.getString("token",""); sessionId=preferences.getString("session","");
  deviceId=preferences.getUInt("device",0); nextSequence=preferences.getUInt("reserved",0); reservedEnd=nextSequence;
  const i2s_config_t config={.mode=static_cast<i2s_mode_t>(I2S_MODE_MASTER|I2S_MODE_RX),.sample_rate=16000,
    .bits_per_sample=I2S_BITS_PER_SAMPLE_32BIT,.channel_format=I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format=I2S_COMM_FORMAT_STAND_I2S,.intr_alloc_flags=ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count=8,.dma_buf_len=256,.use_apll=false,.tx_desc_auto_clear=false,.fixed_mclk=0};
  const i2s_pin_config_t pins={.bck_io_num=I2S_SCK_PIN,.ws_io_num=I2S_WS_PIN,.data_out_num=I2S_PIN_NO_CHANGE,.data_in_num=I2S_SD_PIN};
  if (i2s_driver_install(I2S_NUM_0,&config,0,nullptr)!=ESP_OK || i2s_set_pin(I2S_NUM_0,&pins)!=ESP_OK) { Serial.println("I2S initialization failed"); return; }
  packets=xQueueCreate(4,sizeof(Packet)); if (!packets) { Serial.println("Queue allocation failed"); return; }
  NimBLEDevice::init("Psycon-Ear"); NimBLEDevice::setMTU(517);
  NimBLEDevice::setSecurityAuth(true,true,true); NimBLEDevice::setSecurityIOCap(BLE_HS_IO_DISPLAY_ONLY);
  uint32_t passkey=esp_random()%1000000; NimBLEDevice::setSecurityPasskey(passkey);
  Serial.printf("BLE pairing passkey: %06lu\n",static_cast<unsigned long>(passkey));
  auto *server=NimBLEDevice::createServer(); auto *service=server->createService("7f4d1001-69f5-4a4f-a673-9c18f5d00100");
  statusCharacteristic=service->createCharacteristic("7f4d1002-69f5-4a4f-a673-9c18f5d00100",NIMBLE_PROPERTY::READ|NIMBLE_PROPERTY::NOTIFY|NIMBLE_PROPERTY::WRITE|NIMBLE_PROPERTY::WRITE_ENC|NIMBLE_PROPERTY::WRITE_AUTHEN,1800);
  statusCharacteristic->setCallbacks(new Controls()); statusCharacteristic->setValue("paused: use bonded BLE resume");
  service->start(); auto *advertising=NimBLEDevice::getAdvertising(); advertising->addServiceUUID(service->getUUID()); advertising->start();
  WiFi.mode(WIFI_STA);
  if (xTaskCreatePinnedToCore(captureTask,"capture",24000,nullptr,2,nullptr,1)!=pdPASS ||
      xTaskCreatePinnedToCore(networkTask,"network",24000,nullptr,1,nullptr,0)!=pdPASS) paused=true;
}
void loop() {
  if (provisioning && millis()>60000) provisioning=false;
  if (rebootRequested) { delay(250); ESP.restart(); }
  delay(100);
}
