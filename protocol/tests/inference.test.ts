import { describe, expect, it } from "vitest";
import { predictStress, scoreToState, validateFeatureWindow, validateSensorPacket } from "../src";
import type { FeatureWindow, ModelArtifact, SensorPacket } from "../src";

const model: ModelArtifact = {
  modelName: "fixture",
  modelVersion: "0.0.1",
  featureNames: ["eda_mean", "acc_mag_mean"],
  classMapping: { "0": "calm", "1": "high_stress" },
  scoreThresholds: {
    calm: [0, 0.3],
    mild_stress: [0.3, 0.6],
    high_stress: [0.6, 1],
  },
  scaler: {
    mean: [1, 10],
    scale: [1, 2],
  },
  logisticRegression: {
    coefficients: [2, 1],
    intercept: -1,
  },
};

describe("protocol inference", () => {
  it("maps scores to three Psycon output states", () => {
    expect(scoreToState(0.1)).toBe("calm");
    expect(scoreToState(0.4)).toBe("mild_stress");
    expect(scoreToState(0.8)).toBe("high_stress");
  });

  it("predicts stress from a logistic model artifact", () => {
    const window: FeatureWindow = {
      windowStartMs: 1000,
      windowEndMs: 6000,
      features: { eda_mean: 2, acc_mag_mean: 12 },
    };
    const prediction = predictStress(model, window);
    expect(prediction.state).toBe("high_stress");
    expect(prediction.score).toBeGreaterThan(0.85);
    expect(prediction.windowStartMs).toBe(1000);
  });

  it("rejects malformed feature windows", () => {
    expect(() => validateFeatureWindow({ windowStartMs: 10, windowEndMs: 5, features: {} })).toThrow();
  });

  it("validates sensor packets", () => {
    const packet: SensorPacket = {
      protocolVersion: 1,
      moduleId: "wrist",
      sequence: 7,
      deviceTimestampMs: 1234,
      payloadType: "wrist_sample",
      payload: { eda: 0.5 },
    };
    expect(() => validateSensorPacket(packet)).not.toThrow();
    expect(() => validateSensorPacket({ ...packet, moduleId: "phone" })).toThrow();
  });
});

