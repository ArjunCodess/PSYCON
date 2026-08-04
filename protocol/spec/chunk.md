# Psycon binary chunk protocol v2

Status: frozen for Week 1. All multibyte integers are little-endian. A packet is exactly one fixed header followed by one stream-specific payload; no padding or trailer is permitted.

## Fixed header

The header is 40 bytes.

| Offset | Width | Field | Type | Unit and rule |
|---:|---:|---|---|---|
| 0 | 4 | `magic` | 4 bytes | ASCII `PSY2` (`50 53 59 32`) |
| 4 | 1 | `protocol_version` | unsigned 8-bit | Must equal `2` |
| 5 | 1 | `header_length` | unsigned 8-bit | Must equal `40` |
| 6 | 1 | `stream_type` | unsigned 8-bit | `1` = `audio_pcm`; `2` = `wrist_batch` |
| 7 | 1 | `flags` | unsigned 8-bit | Must equal `0`; all bits are reserved |
| 8 | 4 | `device_id` | unsigned 32-bit | Stable provisioned device/module identifier |
| 12 | 4 | `sequence` | unsigned 32-bit | Per-device, per-stream chunk sequence; wraps modulo 2^32 |
| 16 | 8 | `device_timestamp_us` | unsigned 64-bit | Device monotonic microseconds at the first sample; not Unix time |
| 24 | 4 | `sample_count` | unsigned 32-bit | Samples or records in the payload; must be nonzero |
| 28 | 4 | `sample_period_us` | unsigned 32-bit | Nominal microseconds between sample starts; must be nonzero |
| 32 | 4 | `payload_length` | unsigned 32-bit | Payload bytes; maximum 65,536 |
| 36 | 4 | `crc32` | unsigned 32-bit | CRC described below |

The complete packet length must equal `40 + payload_length`. Decoders reject unknown versions, stream types, flag bits, excess bytes, truncated bytes, and payloads above 65,536 bytes.

`device_timestamp_us + sample_index_within_chunk * sample_period_us` gives a nominal sample time. Timing quality and gaps are reported separately by acquisition metadata; consumers must not silently replace missing physical readings with zero.

## Checksum

`crc32` uses CRC-32/ISO-HDLC (the common Ethernet/ZIP CRC-32):

- reflected polynomial: `0xedb88320`
- initial register: `0xffffffff`
- input and output reflected: yes
- final XOR: `0xffffffff`
- check value for ASCII `123456789`: `0xcbf43926`

Coverage is the concatenation of header bytes `0..35` and every payload byte (`40..packet_length-1`), in wire order. The stored CRC field at bytes `36..39` is excluded. The four checksum bytes themselves are stored little-endian.

## Stream payloads

### `audio_pcm` (`stream_type = 1`)

The payload is mono PCM with exactly `sample_count` consecutive signed 16-bit little-endian values. Values are raw full-scale PCM counts in the inclusive range -32,768 through 32,767. `payload_length` must equal `sample_count * 2`, so the maximum audio count is 32,768 samples.

The sampling rate is represented without floating point as `1,000,000 / sample_period_us` Hz. Rates that cannot be expressed by an integer-microsecond period are outside v2.

### `wrist_batch` (`stream_type = 2`)

The payload contains exactly `sample_count` consecutive 16-byte records:

| Record offset | Width | Field | Type | Unit and rule |
|---:|---:|---|---|---|
| 0 | 4 | `sample_index` | unsigned 32-bit | Device sample counter; wraps modulo 2^32 |
| 4 | 4 | `ppg_red` | unsigned 32-bit | MAX30102 red-channel raw ADC count |
| 8 | 4 | `ppg_ir` | unsigned 32-bit | MAX30102 IR-channel raw ADC count |
| 12 | 2 | `eda_adc` | unsigned 16-bit | ADS1115/raw front-end ADC code; electrically disconnected until an approved GSR front-end exists |
| 14 | 2 | `temperature_centi_c` | signed 16-bit | Local/skin-adjacent temperature in 0.01 °C |

`payload_length` must equal `sample_count * 16`, so the maximum wrist count is 4,096 records. Raw ADC values do not imply calibrated physiological units. `eda_adc` must not be populated from a person while the front-end is electrically blocked.

## Idempotency and ingest responses

The immutable chunk key is `(device_id, stream_type, sequence)`.

- A first valid upload stores the exact packet bytes and returns HTTP `201` with `{"status":"accepted"}`.
- A retry with the same immutable key, packet length, and CRC returns HTTP `200` with `{"status":"already_present"}` and does not write another object or metadata row.
- The same immutable key with a different packet length or CRC returns HTTP `409` with error code `sequence_conflict`. It must never replace the existing object.

Before storage, ingestion validates authentication, content type, request size, every header constraint, stream-specific length, and CRC. Error bodies are JSON:

```json
{"status":"error","error":{"code":"invalid_crc","message":"Protocol v2 CRC mismatch"}}
```

The message may add safe diagnostic detail but must not contain API keys, raw audio, or other payload values.

| HTTP | Error code | Condition |
|---:|---|---|
| 400 | `invalid_header` | Bad magic/header length/flags, zero sampling metadata, truncation, or trailing bytes |
| 400 | `unsupported_version` | `protocol_version` is not 2 |
| 400 | `unsupported_stream` | `stream_type` is not 1 or 2 |
| 400 | `invalid_payload` | Payload width/count is invalid for the stream |
| 400 | `invalid_crc` | Stored and computed CRC differ |
| 401 | `unauthorized` | Missing or invalid device credential |
| 409 | `sequence_conflict` | Immutable key already exists with a different length or CRC |
| 413 | `payload_too_large` | Declared payload exceeds 65,536 bytes or request exceeds 65,576 bytes |
| 415 | `unsupported_media_type` | Content type is not `application/vnd.psycon.chunk-v2` |
| 500 | `storage_error` | Durable storage or metadata commit failed; no success is reported |

Clients may retry network failures and `500` responses with identical bytes. They must not reuse an immutable key for changed bytes.

## Canonical fixtures

The files under `protocol/fixtures/` are contract artifacts. `protocol/tools/generate_fixtures.py` deterministically regenerates them. `audio.bin` and `wrist.bin` must decode successfully; `invalid_crc.bin` is the audio fixture with its final payload bit flipped and must fail CRC validation in every implementation.

### `audio.bin`

Decoded values:

| Field | Value |
|---|---:|
| Packet length | 56 bytes |
| Device ID | `0xe001a001` |
| Sequence | 42 |
| Device timestamp | 1,700,000,000,123,456 µs |
| Sample count | 8 |
| Sample period | 125 µs (8,000 Hz) |
| Payload length | 16 bytes |
| CRC-32 | `0xbaa9f379` |
| PCM samples | `[-32768, -12345, -1, 0, 1, 12345, 32767, 2048]` |

Payload hex:

```text
00 80 c7 cf ff ff 00 00 01 00 39 30 ff 7f 00 08
```

Complete packet hex:

```text
50 53 59 32 02 28 01 00 01 a0 01 e0 2a 00 00 00
40 22 20 18 24 0a 06 00 08 00 00 00 7d 00 00 00
10 00 00 00 79 f3 a9 ba 00 80 c7 cf ff ff 00 00
01 00 39 30 ff 7f 00 08
```

### `wrist.bin`

Decoded values:

| Field | Value |
|---|---:|
| Packet length | 72 bytes |
| Device ID | `0xb001c002` |
| Sequence | 7 |
| Device timestamp | 1,700,000,000,999,000 µs |
| Sample count | 2 |
| Sample period | 40,000 µs (25 Hz) |
| Payload length | 32 bytes |
| CRC-32 | `0x0ba0f731` |

Decoded records:

| `sample_index` | `ppg_red` | `ppg_ir` | `eda_adc` | `temperature_centi_c` |
|---:|---:|---:|---:|---:|
| 1000 | 50000 | 60000 | 1234 | 3150 |
| 1001 | 50010 | 60020 | 1240 | 3155 |

Payload hex:

```text
e8 03 00 00 50 c3 00 00 60 ea 00 00 d2 04 4e 0c
e9 03 00 00 5a c3 00 00 74 ea 00 00 d8 04 53 0c
```

Complete packet hex:

```text
50 53 59 32 02 28 02 00 02 c0 01 b0 07 00 00 00
58 7e 2d 18 24 0a 06 00 02 00 00 00 40 9c 00 00
20 00 00 00 31 f7 a0 0b e8 03 00 00 50 c3 00 00
60 ea 00 00 d2 04 4e 0c e9 03 00 00 5a c3 00 00
74 ea 00 00 d8 04 53 0c
```
