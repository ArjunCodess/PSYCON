import type { FeatureWindow, ModelArtifact, SensorPacket } from "./types";

export function validateSensorPacket(packet: unknown): asserts packet is SensorPacket {
  if (!isRecord(packet)) throw new Error("SensorPacket must be an object");
  if (packet.protocolVersion !== 1) throw new Error("Unsupported protocolVersion");
  if (packet.moduleId !== "wrist" && packet.moduleId !== "ear") throw new Error("Invalid moduleId");
  if (!Number.isInteger(packet.sequence) || packet.sequence < 0) throw new Error("Invalid sequence");
  if (typeof packet.deviceTimestampMs !== "number") throw new Error("Invalid deviceTimestampMs");
  if (!["wrist_sample", "audio_features", "status"].includes(String(packet.payloadType))) throw new Error("Invalid payloadType");
  if (!isRecord(packet.payload)) throw new Error("Invalid payload");
}

export function validateFeatureWindow(window: unknown): asserts window is FeatureWindow {
  if (!isRecord(window)) throw new Error("FeatureWindow must be an object");
  if (typeof window.windowStartMs !== "number") throw new Error("Invalid windowStartMs");
  if (typeof window.windowEndMs !== "number") throw new Error("Invalid windowEndMs");
  if (window.windowEndMs <= window.windowStartMs) throw new Error("windowEndMs must be after windowStartMs");
  if (!isRecord(window.features)) throw new Error("features must be an object");
  for (const [name, value] of Object.entries(window.features)) {
    if (!name || typeof value !== "number" || !Number.isFinite(value)) {
      throw new Error(`Invalid feature ${name}`);
    }
  }
}

export function validateModelArtifact(model: unknown): asserts model is ModelArtifact {
  if (!isRecord(model)) throw new Error("ModelArtifact must be an object");
  if (typeof model.modelName !== "string") throw new Error("Invalid modelName");
  if (typeof model.modelVersion !== "string") throw new Error("Invalid modelVersion");
  if (!Array.isArray(model.featureNames) || !model.featureNames.every((f) => typeof f === "string")) throw new Error("Invalid featureNames");
  if (!isRecord(model.scaler) || !Array.isArray(model.scaler.mean) || !Array.isArray(model.scaler.scale)) throw new Error("Invalid scaler");
  if (!isRecord(model.logisticRegression) || !Array.isArray(model.logisticRegression.coefficients)) throw new Error("Invalid logisticRegression");
  if (model.featureNames.length !== model.scaler.mean.length || model.featureNames.length !== model.scaler.scale.length) throw new Error("Scaler length mismatch");
  if (model.featureNames.length !== model.logisticRegression.coefficients.length) throw new Error("Coefficient length mismatch");
}

function isRecord(value: unknown): value is Record<string, any> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

