import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { validateWristBatch } from "../src";

const fixture = JSON.parse(
  readFileSync(fileURLToPath(new URL("../fixtures/wrist_batch.json", import.meta.url)), "utf8"),
);

describe("normalized wrist batches", () => {
  it("accepts the canonical fixture", () => {
    expect(() => validateWristBatch(fixture)).not.toThrow();
  });

  it("rejects gaps without an increasing sample index", () => {
    const invalid = { ...fixture, samples: [fixture.samples[1], fixture.samples[0]] };
    expect(() => validateWristBatch(invalid)).toThrow("sampleIndex");
  });

  it("rejects unknown quality bits", () => {
    const invalid = { ...fixture, samples: [{ ...fixture.samples[0], qualityFlags: 128 }] };
    expect(() => validateWristBatch(invalid)).toThrow("range");
  });
});
