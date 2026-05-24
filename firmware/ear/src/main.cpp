#include <Arduino.h>
#include <NimBLEDevice.h>
#include "driver/i2s.h"

static const int I2S_WS_PIN = 25;
static const int I2S_SCK_PIN = 26;
static const int I2S_SD_PIN = 33;
static const i2s_port_t I2S_PORT = I2S_NUM_0;

static const char *DEVICE_NAME = "Psycon-Ear";
static const char *SERVICE_UUID = "7f4d1001-69f5-4a4f-a673-9c18f5d00100";
static const char *AUDIO_FEATURE_CHAR_UUID = "7f4d1002-69f5-4a4f-a673-9c18f5d00100";

struct __attribute__((packed)) AudioFeaturePacket {
  uint8_t protocolVersion;
  uint8_t moduleId;
  uint32_t sequence;
  uint32_t deviceTimestampMs;
  float rms;
  float energy;
  float zeroCrossingRate;
};

NimBLECharacteristic *audioFeatureCharacteristic = nullptr;
uint32_t sequenceNumber = 0;

void setupI2S() {
  const i2s_config_t i2sConfig = {
      .mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_RX),
      .sample_rate = 16000,
      .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
      .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
      .communication_format = I2S_COMM_FORMAT_STAND_I2S,
      .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
      .dma_buf_count = 4,
      .dma_buf_len = 256,
      .use_apll = false,
      .tx_desc_auto_clear = false,
      .fixed_mclk = 0};

  const i2s_pin_config_t pinConfig = {
      .bck_io_num = I2S_SCK_PIN,
      .ws_io_num = I2S_WS_PIN,
      .data_out_num = I2S_PIN_NO_CHANGE,
      .data_in_num = I2S_SD_PIN};

  i2s_driver_install(I2S_PORT, &i2sConfig, 0, nullptr);
  i2s_set_pin(I2S_PORT, &pinConfig);
  i2s_zero_dma_buffer(I2S_PORT);
}

void setupBle() {
  NimBLEDevice::init(DEVICE_NAME);
  NimBLEServer *server = NimBLEDevice::createServer();
  NimBLEService *service = server->createService(SERVICE_UUID);
  audioFeatureCharacteristic = service->createCharacteristic(
      AUDIO_FEATURE_CHAR_UUID,
      NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);

  NimBLEAdvertising *advertising = NimBLEDevice::getAdvertising();
  advertising->addServiceUUID(SERVICE_UUID);
  advertising->setName(DEVICE_NAME);
  advertising->start();
  Serial.println("BLE advertising started for Psycon ear module");
}

AudioFeaturePacket readAudioFeatures() {
  constexpr size_t sampleCount = 256;
  int32_t samples[sampleCount];
  size_t bytesRead = 0;
  i2s_read(I2S_PORT, samples, sizeof(samples), &bytesRead, pdMS_TO_TICKS(100));
  const size_t count = bytesRead / sizeof(int32_t);

  double sumSquares = 0.0;
  double sumAbs = 0.0;
  uint32_t zeroCrossings = 0;
  int32_t previous = 0;

  for (size_t i = 0; i < count; i++) {
    int32_t sample = samples[i] >> 14;
    sumSquares += static_cast<double>(sample) * static_cast<double>(sample);
    sumAbs += abs(sample);
    if (i > 0 && ((sample >= 0 && previous < 0) || (sample < 0 && previous >= 0))) {
      zeroCrossings++;
    }
    previous = sample;
  }

  AudioFeaturePacket packet;
  packet.protocolVersion = 1;
  packet.moduleId = 2;
  packet.sequence = sequenceNumber++;
  packet.deviceTimestampMs = millis();
  packet.rms = count > 0 ? sqrt(sumSquares / count) : 0.0f;
  packet.energy = count > 0 ? sumAbs / count : 0.0f;
  packet.zeroCrossingRate = count > 1 ? static_cast<float>(zeroCrossings) / static_cast<float>(count - 1) : 0.0f;
  return packet;
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("Psycon ear firmware booting");
  Serial.println("INMP441 pins: WS=25 SCK=26 SD=33 L/R=GND");
  setupI2S();
  setupBle();
}

void loop() {
  AudioFeaturePacket packet = readAudioFeatures();
  Serial.print("seq=");
  Serial.print(packet.sequence);
  Serial.print(" t=");
  Serial.print(packet.deviceTimestampMs);
  Serial.print(" rms=");
  Serial.print(packet.rms, 2);
  Serial.print(" energy=");
  Serial.print(packet.energy, 2);
  Serial.print(" zcr=");
  Serial.println(packet.zeroCrossingRate, 4);

  if (audioFeatureCharacteristic != nullptr) {
    audioFeatureCharacteristic->setValue(reinterpret_cast<uint8_t *>(&packet), sizeof(packet));
    audioFeatureCharacteristic->notify();
  }

  delay(250);
}
