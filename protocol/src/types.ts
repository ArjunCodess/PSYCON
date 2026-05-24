export type StressState = "calm" | "mild_stress" | "high_stress" | "unknown";

export type ModuleId = "wrist" | "ear";

export type SensorPacket = {
  protocolVersion: number;
  moduleId: ModuleId;
  sequence: number;
  deviceTimestampMs: number;
  phoneReceivedTimestampMs?: number;
  payloadType: "wrist_sample" | "audio_features" | "status";
  payload: Record<string, number | string | boolean | null>;
  checksum?: number;
};

export type FeatureWindow = {
  subject?: string;
  sessionId?: string;
  windowStartMs: number;
  windowEndMs: number;
  features: Record<string, number>;
  label?: StressState;
};

export type Prediction = {
  score: number;
  state: Exclude<StressState, "unknown">;
  modelName: string;
  modelVersion: string;
  windowStartMs: number;
  windowEndMs: number;
};

export type ModelArtifact = {
  modelName: string;
  modelVersion: string;
  featureNames: string[];
  classMapping: Record<string, StressState>;
  scoreThresholds: Record<string, [number, number]>;
  scaler: {
    mean: number[];
    scale: number[];
  };
  logisticRegression: {
    coefficients: number[];
    intercept: number;
  };
  baseline?: Record<string, unknown>;
  trainingMetadata?: Record<string, unknown>;
};

