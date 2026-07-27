import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { crc32ChunkV2, decodeChunkV2 } from "../src";

const fixture = (name: string): Uint8Array =>
  readFileSync(fileURLToPath(new URL(`../fixtures/${name}`, import.meta.url)));

const changed = (packet: Uint8Array, offset: number, value: number): Uint8Array => {
  const copy = packet.slice();
  copy[offset] = value;
  return copy;
};

describe("Protocol v2 chunks", () => {
  it("decodes the audio fixture exactly", () => {
    const chunk = decodeChunkV2(fixture("audio.bin"));

    expect(chunk.streamType).toBe("audio_pcm");
    if (chunk.streamType !== "audio_pcm") throw new Error("expected audio chunk");
    expect(chunk.header).toEqual({
      protocolVersion: 2,
      headerLength: 40,
      streamType: "audio_pcm",
      flags: 0,
      deviceId: 0xe001a001,
      sequence: 42,
      deviceTimestampUs: 1700000000123456n,
      sampleCount: 8,
      samplePeriodUs: 125,
      payloadLength: 16,
      crc32: 0xbaa9f379,
    });
    expect(chunk.samples).toEqual([-32768, -12345, -1, 0, 1, 12345, 32767, 2048]);
  });

  it("decodes the wrist fixture exactly", () => {
    const chunk = decodeChunkV2(fixture("wrist.bin"));

    expect(chunk.streamType).toBe("wrist_batch");
    if (chunk.streamType !== "wrist_batch") throw new Error("expected wrist chunk");
    expect(chunk.header).toEqual({
      protocolVersion: 2,
      headerLength: 40,
      streamType: "wrist_batch",
      flags: 0,
      deviceId: 0xb001c002,
      sequence: 7,
      deviceTimestampUs: 1700000000999000n,
      sampleCount: 2,
      samplePeriodUs: 40000,
      payloadLength: 32,
      crc32: 0x0ba0f731,
    });
    expect(chunk.samples).toEqual([
      { sampleIndex: 1000, ppgRed: 50000, ppgIr: 60000, edaAdc: 1234, temperatureCentiC: 3150 },
      { sampleIndex: 1001, ppgRed: 50010, ppgIr: 60020, edaAdc: 1240, temperatureCentiC: 3155 },
    ]);
  });

  it.each([
    ["short header", new Uint8Array(39), "shorter than"],
    ["bad magic", changed(fixture("audio.bin"), 0, 0), "magic"],
    ["unsupported version", changed(fixture("audio.bin"), 4, 3), "version"],
    ["wrong header length", changed(fixture("audio.bin"), 5, 39), "header length"],
    ["unknown stream", changed(fixture("audio.bin"), 6, 9), "stream type"],
    ["unknown flags", changed(fixture("audio.bin"), 7, 1), "flags"],
    ["wrong payload length", changed(fixture("audio.bin"), 32, 15), "packet length"],
    ["checksum mismatch", changed(fixture("audio.bin"), 40, 1), "CRC"],
  ])("rejects %s", (_name, packet, message) => {
    expect(() => decodeChunkV2(packet)).toThrow(message);
  });

  it("rejects a structurally invalid audio payload with a valid checksum", () => {
    const packet = fixture("audio.bin").slice(0, -1);
    const view = new DataView(packet.buffer, packet.byteOffset, packet.byteLength);
    view.setUint32(32, 15, true);
    view.setUint32(24, 8, true);
    view.setUint32(36, crc32ChunkV2(packet), true);
    expect(() => decodeChunkV2(packet)).toThrow("audio payload");
  });
});
