#include <Arduino.h>
#include <NimBLEDevice.h>
#include <Wire.h>

static const int SDA_PIN = 21;
static const int SCL_PIN = 22;
static const uint8_t ADS1115_ADDR = 0x48;

static const char *DEVICE_NAME = "Psycon-Wrist";
static const char *SERVICE_UUID = "7f4d0001-69f5-4a4f-a673-9c18f5d00100";
static const char *SENSOR_CHAR_UUID = "7f4d0002-69f5-4a4f-a673-9c18f5d00100";

struct __attribute__((packed)) WristPacket {
  uint8_t protocolVersion;
  uint8_t moduleId;
  uint32_t sequence;
  uint32_t deviceTimestampMs;
  float bvp;
  float eda;
  float accX;
  float accY;
  float accZ;
};

NimBLECharacteristic *sensorCharacteristic = nullptr;
uint32_t sequenceNumber = 0;

void scanI2CBus() {
  Serial.println("Scanning I2C bus on SDA=21 SCL=22");
  for (uint8_t address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    if (Wire.endTransmission() == 0) {
      Serial.print("Found I2C device at 0x");
      Serial.println(address, HEX);
    }
  }
}

void setupBle() {
  NimBLEDevice::init(DEVICE_NAME);
  NimBLEServer *server = NimBLEDevice::createServer();
  NimBLEService *service = server->createService(SERVICE_UUID);
  sensorCharacteristic = service->createCharacteristic(
      SENSOR_CHAR_UUID,
      NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);

  NimBLEAdvertising *advertising = NimBLEDevice::getAdvertising();
  advertising->addServiceUUID(SERVICE_UUID);
  advertising->setName(DEVICE_NAME);
  advertising->start();
  Serial.println("BLE advertising started for Psycon wrist module");
}

WristPacket readWristPacket() {
  // Sensor drivers will replace these placeholders after board bring-up.
  WristPacket packet;
  packet.protocolVersion = 1;
  packet.moduleId = 1;
  packet.sequence = sequenceNumber++;
  packet.deviceTimestampMs = millis();
  packet.bvp = 0.0f;
  packet.eda = 0.0f;
  packet.accX = 0.0f;
  packet.accY = 0.0f;
  packet.accZ = 1.0f;
  return packet;
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("Psycon wrist firmware booting");
  Wire.begin(SDA_PIN, SCL_PIN);
  scanI2CBus();
  Serial.print("Expected ADS1115 GSR address: 0x");
  Serial.println(ADS1115_ADDR, HEX);
  setupBle();
}

void loop() {
  WristPacket packet = readWristPacket();
  Serial.print("seq=");
  Serial.print(packet.sequence);
  Serial.print(" t=");
  Serial.print(packet.deviceTimestampMs);
  Serial.print(" bvp=");
  Serial.print(packet.bvp, 4);
  Serial.print(" eda=");
  Serial.print(packet.eda, 4);
  Serial.print(" acc=(");
  Serial.print(packet.accX, 3);
  Serial.print(",");
  Serial.print(packet.accY, 3);
  Serial.print(",");
  Serial.print(packet.accZ, 3);
  Serial.println(")");

  if (sensorCharacteristic != nullptr) {
    sensorCharacteristic->setValue(reinterpret_cast<uint8_t *>(&packet), sizeof(packet));
    sensorCharacteristic->notify();
  }

  delay(250);
}
