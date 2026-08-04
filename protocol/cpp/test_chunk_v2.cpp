#include "chunk_v2.hpp"

#include <cassert>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <vector>

using psycon::protocol::StreamType;

std::vector<std::uint8_t> readFile(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open fixture");
  return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}

int main(int argc, char** argv) {
  if (argc != 2) return 2;
  const std::filesystem::path fixtures(argv[1]);

  const auto audio = psycon::protocol::decodeChunkV2(readFile(fixtures / "audio.bin"));
  assert(audio.header.streamType == StreamType::AudioPcm);
  assert(audio.header.deviceId == 0xe001a001U);
  assert(audio.header.sequence == 42U);
  assert(audio.header.deviceTimestampUs == 1700000000123456ULL);
  assert((audio.audioSamples == std::vector<std::int16_t>{-32768, -12345, -1, 0, 1, 12345, 32767, 2048}));

  const auto wrist = psycon::protocol::decodeChunkV2(readFile(fixtures / "wrist.bin"));
  assert(wrist.header.streamType == StreamType::WristBatch);
  assert(wrist.header.deviceId == 0xb001c002U);
  assert(wrist.wristSamples.size() == 2U);
  assert(wrist.wristSamples[0].sampleIndex == 1000U);
  assert(wrist.wristSamples[1].temperatureCentiC == 3155);

  bool rejected = false;
  try {
    psycon::protocol::decodeChunkV2(readFile(fixtures / "invalid_crc.bin"));
  } catch (const std::runtime_error&) {
    rejected = true;
  }
  assert(rejected);
  return 0;
}
