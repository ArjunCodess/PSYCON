// Binary chunk codec; protocol-version checks remain part of the wire contract.
import type {
  AudioChunkV2,
  ChunkStreamType,
  ChunkV2,
  ChunkV2Header,
  WristChunkV2,
  WristSampleV2,
} from "./types";

export const CHUNK_V2_HEADER_LENGTH = 40;
export const CHUNK_V2_MAX_PAYLOAD_LENGTH = 65_536;

const AUDIO_STREAM = 1;
const WRIST_STREAM = 2;
const WRIST_RECORD_LENGTH = 16;

const streamTypeFromCode = (code: number): ChunkStreamType => {
  if (code === AUDIO_STREAM) return "audio_pcm";
  if (code === WRIST_STREAM) return "wrist_batch";
  throw new Error(`unsupported Protocol v2 stream type: ${code}`);
};

const updateCrc32 = (crc: number, bytes: Uint8Array): number => {
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
  }
  return crc >>> 0;
};

/**
 * Compute CRC-32/ISO-HDLC over header bytes 0..35 followed by the payload.
 * The stored checksum at bytes 36..39 is deliberately excluded.
 */
export const crc32ChunkV2 = (packet: Uint8Array): number => {
  if (packet.byteLength < CHUNK_V2_HEADER_LENGTH) {
    throw new Error("Protocol v2 packet is shorter than its 40-byte header");
  }
  let crc = updateCrc32(0xffffffff, packet.subarray(0, 36));
  crc = updateCrc32(crc, packet.subarray(CHUNK_V2_HEADER_LENGTH));
  return (crc ^ 0xffffffff) >>> 0;
};

const decodeHeader = (packet: Uint8Array): ChunkV2Header => {
  if (packet.byteLength < CHUNK_V2_HEADER_LENGTH) {
    throw new Error("Protocol v2 packet is shorter than its 40-byte header");
  }

  const view = new DataView(packet.buffer, packet.byteOffset, packet.byteLength);
  const magic = String.fromCharCode(...packet.subarray(0, 4));
  if (magic !== "PSY2") throw new Error(`invalid Protocol v2 magic: ${JSON.stringify(magic)}`);

  const protocolVersion = view.getUint8(4);
  if (protocolVersion !== 2) throw new Error(`unsupported Protocol version: ${protocolVersion}`);

  const headerLength = view.getUint8(5);
  if (headerLength !== CHUNK_V2_HEADER_LENGTH) {
    throw new Error(`invalid Protocol v2 header length: ${headerLength}`);
  }

  const streamType = streamTypeFromCode(view.getUint8(6));
  const flags = view.getUint8(7);
  if (flags !== 0) throw new Error(`unsupported Protocol v2 flags: ${flags}`);

  const sampleCount = view.getUint32(24, true);
  const samplePeriodUs = view.getUint32(28, true);
  const payloadLength = view.getUint32(32, true);
  if (payloadLength > CHUNK_V2_MAX_PAYLOAD_LENGTH) {
    throw new Error(`Protocol v2 payload exceeds ${CHUNK_V2_MAX_PAYLOAD_LENGTH} bytes`);
  }
  if (packet.byteLength !== CHUNK_V2_HEADER_LENGTH + payloadLength) {
    throw new Error(
      `Protocol v2 packet length ${packet.byteLength} does not match header payload length ${payloadLength}`,
    );
  }
  if (sampleCount === 0) throw new Error("Protocol v2 sample count must be nonzero");
  if (samplePeriodUs === 0) throw new Error("Protocol v2 sample period must be nonzero");

  const crc32 = view.getUint32(36, true);
  const computedCrc32 = crc32ChunkV2(packet);
  if (crc32 !== computedCrc32) {
    throw new Error(
      `Protocol v2 CRC mismatch: stored 0x${crc32.toString(16)}, computed 0x${computedCrc32.toString(16)}`,
    );
  }

  return {
    protocolVersion: 2,
    headerLength: CHUNK_V2_HEADER_LENGTH,
    streamType,
    flags: 0,
    deviceId: view.getUint32(8, true),
    sequence: view.getUint32(12, true),
    deviceTimestampUs: view.getBigUint64(16, true),
    sampleCount,
    samplePeriodUs,
    payloadLength,
    crc32,
  };
};

const decodeAudio = (
  packet: Uint8Array,
  header: ChunkV2Header & { streamType: "audio_pcm" },
): AudioChunkV2 => {
  if (header.payloadLength !== header.sampleCount * 2) {
    throw new Error("Protocol v2 audio payload must contain one signed 16-bit value per sample");
  }
  const view = new DataView(packet.buffer, packet.byteOffset + CHUNK_V2_HEADER_LENGTH, header.payloadLength);
  const samples = Array.from({ length: header.sampleCount }, (_, index) => view.getInt16(index * 2, true));
  return { streamType: "audio_pcm", header, samples };
};

const decodeWrist = (
  packet: Uint8Array,
  header: ChunkV2Header & { streamType: "wrist_batch" },
): WristChunkV2 => {
  if (header.payloadLength !== header.sampleCount * WRIST_RECORD_LENGTH) {
    throw new Error("Protocol v2 wrist payload must contain one 16-byte record per sample");
  }
  const view = new DataView(packet.buffer, packet.byteOffset + CHUNK_V2_HEADER_LENGTH, header.payloadLength);
  const samples: WristSampleV2[] = Array.from({ length: header.sampleCount }, (_, index) => {
    const offset = index * WRIST_RECORD_LENGTH;
    return {
      sampleIndex: view.getUint32(offset, true),
      ppgRed: view.getUint32(offset + 4, true),
      ppgIr: view.getUint32(offset + 8, true),
      edaAdc: view.getUint16(offset + 12, true),
      temperatureCentiC: view.getInt16(offset + 14, true),
    };
  });
  return { streamType: "wrist_batch", header, samples };
};

export const decodeChunkV2 = (packet: Uint8Array): ChunkV2 => {
  const header = decodeHeader(packet);
  if (header.streamType === "audio_pcm") {
    return decodeAudio(packet, { ...header, streamType: "audio_pcm" });
  }
  return decodeWrist(packet, { ...header, streamType: "wrist_batch" });
};
