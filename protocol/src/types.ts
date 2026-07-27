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

export type ChunkStreamType = "audio_pcm" | "wrist_batch";

export type ChunkV2Header = {
  protocolVersion: 2;
  headerLength: 40;
  streamType: ChunkStreamType;
  flags: 0;
  deviceId: number;
  sequence: number;
  deviceTimestampUs: bigint;
  sampleCount: number;
  samplePeriodUs: number;
  payloadLength: number;
  crc32: number;
};

export type AudioChunkV2 = {
  streamType: "audio_pcm";
  header: ChunkV2Header & { streamType: "audio_pcm" };
  samples: number[];
};

export type WristSampleV2 = {
  sampleIndex: number;
  ppgRed: number;
  ppgIr: number;
  edaAdc: number;
  temperatureCentiC: number;
};

export type WristChunkV2 = {
  streamType: "wrist_batch";
  header: ChunkV2Header & { streamType: "wrist_batch" };
  samples: WristSampleV2[];
};

export type ChunkV2 = AudioChunkV2 | WristChunkV2;
