from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    s3_endpoint_url: str
    s3_public_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str
    s3_region: str
    secret_key: str
    bootstrap_operator_token: str
    model_artifact_path: str
    max_chunk_bytes: int = 65_576
    sync_max_delay_us: int = 2_000_000
    sync_max_uncertainty_us: int = 250_000

    @classmethod
    def from_env(cls, *, testing: bool = False) -> "Settings":
        defaults = {
            "database_url": "postgresql://psycon:psycon@localhost:5432/psycon",
            "s3_endpoint_url": "http://localhost:9000",
            "s3_public_endpoint_url": "http://localhost:9000",
            "s3_access_key": "psycon",
            "s3_secret_key": "psycon-local-secret",
            "s3_bucket": "psycon-research",
            "s3_region": "us-east-1",
            "secret_key": "local-development-secret-change-me",
            "bootstrap_operator_token": "psycon-local-operator",
            "model_artifact_path": "results/app_model.json",
        }
        values = {
            key: os.getenv(f"PSYCON_{key.upper()}", default)
            for key, default in defaults.items()
        }
        settings = cls(**values)
        if not testing:
            weak = {
                defaults["secret_key"],
                defaults["bootstrap_operator_token"],
                defaults["s3_secret_key"],
            }
            if any(value in weak for value in (
                settings.secret_key,
                settings.bootstrap_operator_token,
                settings.s3_secret_key,
            )) and os.getenv("PSYCON_ENV", "development") == "production":
                raise RuntimeError("Production secrets must not use local development defaults")
        return settings
