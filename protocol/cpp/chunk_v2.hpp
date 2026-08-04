#pragma once

#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace psycon::protocol {

constexpr std::size_t kHeaderLength = 40;
constexpr std::uint32_t kMaxPayloadLength = 65536;

enum class StreamType : std::uint8_t { AudioPcm = 1, WristBatch = 2 };

struct Header {
  StreamType streamType;
  std::uint32_t deviceId;
  std::uint32_t sequence;
  std::uint64_t deviceTimestampUs;
  std::uint32_t sampleCount;
  std::uint32_t samplePeriodUs;
  std::uint32_t payloadLength;
  std::uint32_t crc32;
};

struct WristSample {
  std::uint32_t sampleIndex;
  std::uint32_t ppgRed;
  std::uint32_t ppgIr;
  std::uint16_t edaAdc;
  std::int16_t temperatureCentiC;
};

struct Chunk {
  Header header;
  std::vector<std::int16_t> audioSamples;
  std::vector<WristSample> wristSamples;
};

inline std::uint16_t readU16(const std::uint8_t* p) {
  return static_cast<std::uint16_t>(p[0]) |
         (static_cast<std::uint16_t>(p[1]) << 8U);
}

inline std::uint32_t readU32(const std::uint8_t* p) {
  return static_cast<std::uint32_t>(p[0]) |
         (static_cast<std::uint32_t>(p[1]) << 8U) |
         (static_cast<std::uint32_t>(p[2]) << 16U) |
         (static_cast<std::uint32_t>(p[3]) << 24U);
}

inline std::uint64_t readU64(const std::uint8_t* p) {
  return static_cast<std::uint64_t>(readU32(p)) |
         (static_cast<std::uint64_t>(readU32(p + 4)) << 32U);
}

inline std::uint32_t updateCrc32(std::uint32_t crc, const std::uint8_t* data,
                                 std::size_t length) {
  for (std::size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (int bit = 0; bit < 8; ++bit) {
      crc = (crc >> 1U) ^ ((crc & 1U) ? 0xedb88320U : 0U);
    }
  }
  return crc;
}

inline std::uint32_t chunkCrc32(const std::vector<std::uint8_t>& packet) {
  if (packet.size() < kHeaderLength) {
    throw std::runtime_error("Protocol v2 packet is shorter than its header");
  }
  auto crc = updateCrc32(0xffffffffU, packet.data(), 36);
  crc = updateCrc32(crc, packet.data() + kHeaderLength,
                    packet.size() - kHeaderLength);
  return crc ^ 0xffffffffU;
}

inline Chunk decodeChunkV2(const std::vector<std::uint8_t>& packet) {
  if (packet.size() < kHeaderLength) {
    throw std::runtime_error("Protocol v2 packet is shorter than its header");
  }
  if (std::string(reinterpret_cast<const char*>(packet.data()), 4) != "PSY2") {
    throw std::runtime_error("invalid Protocol v2 magic");
  }
  if (packet[4] != 2) throw std::runtime_error("unsupported Protocol version");
  if (packet[5] != kHeaderLength) throw std::runtime_error("invalid header length");
  if (packet[7] != 0) throw std::runtime_error("unsupported flags");

  StreamType streamType;
  if (packet[6] == 1) {
    streamType = StreamType::AudioPcm;
  } else if (packet[6] == 2) {
    streamType = StreamType::WristBatch;
  } else {
    throw std::runtime_error("unsupported stream type");
  }

  const auto sampleCount = readU32(packet.data() + 24);
  const auto samplePeriodUs = readU32(packet.data() + 28);
  const auto payloadLength = readU32(packet.data() + 32);
  const auto storedCrc = readU32(packet.data() + 36);
  if (sampleCount == 0 || samplePeriodUs == 0) {
    throw std::runtime_error("invalid sampling metadata");
  }
  if (payloadLength > kMaxPayloadLength ||
      packet.size() != kHeaderLength + payloadLength) {
    throw std::runtime_error("invalid packet length");
  }
  if (storedCrc != chunkCrc32(packet)) {
    throw std::runtime_error("Protocol v2 CRC mismatch");
  }

  Chunk chunk{{streamType, readU32(packet.data() + 8),
               readU32(packet.data() + 12), readU64(packet.data() + 16),
               sampleCount, samplePeriodUs, payloadLength, storedCrc}, {}, {}};
  const auto* payload = packet.data() + kHeaderLength;
  if (streamType == StreamType::AudioPcm) {
    if (payloadLength != sampleCount * 2U) {
      throw std::runtime_error("invalid audio payload");
    }
    chunk.audioSamples.reserve(sampleCount);
    for (std::uint32_t i = 0; i < sampleCount; ++i) {
      chunk.audioSamples.push_back(static_cast<std::int16_t>(readU16(payload + i * 2U)));
    }
  } else {
    if (payloadLength != sampleCount * 16U) {
      throw std::runtime_error("invalid wrist payload");
    }
    chunk.wristSamples.reserve(sampleCount);
    for (std::uint32_t i = 0; i < sampleCount; ++i) {
      const auto* record = payload + i * 16U;
      chunk.wristSamples.push_back(
          {readU32(record), readU32(record + 4), readU32(record + 8),
           readU16(record + 12), static_cast<std::int16_t>(readU16(record + 14))});
    }
  }
  return chunk;
}

}  // namespace psycon::protocol
