export const WristQuality = {
  ok: 0,
  contactLost: 1 << 0,
  ppgSaturated: 1 << 1,
  edaSaturated: 1 << 2,
  sensorDisconnected: 1 << 3,
  timingGap: 1 << 4,
  batteryLow: 1 << 5,
} as const;

export type WristSample = {
  sampleIndex: number;
  ppgRed: number;
  ppgIr: number;
  edaAdc: number;
  temperatureCentiC: number;
  accelXMg: number;
  accelYMg: number;
  accelZMg: number;
  gyroXDeciDps: number;
  gyroYDeciDps: number;
  gyroZDeciDps: number;
  qualityFlags: number;
};

export type WristBatch = {
  sessionId: string;
  deviceId: number;
  sequence: number;
  deviceTimestampUs: number;
  samplePeriodUs: number;
  batteryMv: number;
  samples: WristSample[];
  errors: WristError[];
};

export type WristError = {
  code: string;
  sensor: string;
  message: string;
  recoverable: boolean;
  observedAtSample?: number;
};

export type CalibrationRecord = {
  calibrationId: string;
  deviceId: number;
  firmwareVersion: string;
  hardwareRevision: string;
  calibratedAt: string;
  operator: string;
  method: string;
  environment: string;
  result: string;
};

const unsignedInteger = (value: unknown): value is number =>
  Number.isSafeInteger(value) && Number(value) >= 0;

export function validateWristBatch(value: unknown): asserts value is WristBatch {
  if (typeof value !== "object" || value === null) throw new Error("WristBatch must be an object");
  const batch = value as Record<string, unknown>;
  if (typeof batch.sessionId !== "string" || !batch.sessionId.trim()) throw new Error("Invalid sessionId");
  if (!unsignedInteger(batch.deviceId) || !unsignedInteger(batch.sequence) || !unsignedInteger(batch.deviceTimestampUs)) {
    throw new Error("Invalid wrist batch identity");
  }
  if (!unsignedInteger(batch.samplePeriodUs) || Number(batch.samplePeriodUs) === 0) throw new Error("Invalid samplePeriodUs");
  if (!unsignedInteger(batch.batteryMv) || Number(batch.batteryMv) < 2000 || Number(batch.batteryMv) > 5000) {
    throw new Error("Invalid batteryMv");
  }
  if (!Array.isArray(batch.samples) || batch.samples.length === 0) throw new Error("Wrist batch needs samples");
  if (!Array.isArray(batch.errors)) throw new Error("Invalid errors");
  for (const raw of batch.errors) {
    if (typeof raw !== "object" || raw === null) throw new Error("Invalid wrist error");
    const error = raw as Record<string, unknown>;
    if (!["code", "sensor", "message"].every((field) => typeof error[field] === "string" && String(error[field]).trim())) {
      throw new Error("Invalid wrist error text");
    }
    if (typeof error.recoverable !== "boolean") throw new Error("Invalid wrist error recovery flag");
    if (error.observedAtSample !== undefined && !unsignedInteger(error.observedAtSample)) throw new Error("Invalid wrist error sample");
  }

  let previous = -1;
  const allowedFlags = 0x3f;
  for (const raw of batch.samples) {
    if (typeof raw !== "object" || raw === null) throw new Error("Invalid wrist sample");
    const sample = raw as Record<string, unknown>;
    for (const field of ["sampleIndex", "ppgRed", "ppgIr", "edaAdc", "qualityFlags"] as const) {
      if (!unsignedInteger(sample[field])) throw new Error(`Invalid ${field}`);
    }
    for (const field of ["temperatureCentiC", "accelXMg", "accelYMg", "accelZMg", "gyroXDeciDps", "gyroYDeciDps", "gyroZDeciDps"] as const) {
      if (!Number.isSafeInteger(sample[field])) throw new Error(`Invalid ${field}`);
    }
    if (Number(sample.sampleIndex) <= previous) throw new Error("sampleIndex must increase");
    if (Number(sample.edaAdc) > 65535 || (Number(sample.qualityFlags) & ~allowedFlags) !== 0) throw new Error("Invalid wrist sample range");
    previous = Number(sample.sampleIndex);
  }
}
