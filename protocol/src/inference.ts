import type { FeatureWindow, ModelArtifact, Prediction } from "./types";
import { validateFeatureWindow, validateModelArtifact } from "./validation";

export function predictStress(model: ModelArtifact, window: FeatureWindow): Prediction {
  validateModelArtifact(model);
  validateFeatureWindow(window);

  let logit = model.logisticRegression.intercept;
  model.featureNames.forEach((featureName, index) => {
    const raw = window.features[featureName] ?? 0;
    const scale = model.scaler.scale[index] || 1;
    const normalized = (raw - model.scaler.mean[index]) / scale;
    logit += normalized * model.logisticRegression.coefficients[index];
  });

  const score = sigmoid(logit);
  return {
    score,
    state: scoreToState(score),
    modelName: model.modelName,
    modelVersion: model.modelVersion,
    windowStartMs: window.windowStartMs,
    windowEndMs: window.windowEndMs,
  };
}

export function scoreToState(score: number): Prediction["state"] {
  if (score < 0.3) return "calm";
  if (score < 0.6) return "mild_stress";
  return "high_stress";
}

function sigmoid(value: number): number {
  return 1 / (1 + Math.exp(-value));
}

