from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from .config import Settings


@dataclass(frozen=True)
class StoredObject:
    key: str
    sha256: str
    size: int


class ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        arguments = dict(
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            **arguments,
        )
        self.public_client = boto3.client(
            "s3",
            endpoint_url=settings.s3_public_endpoint_url,
            **arguments,
        )

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            try:
                self.client.create_bucket(Bucket=self.bucket)
            except ClientError as error:
                if error.response.get("Error", {}).get("Code") not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                    raise

    def put_immutable(self, key: str, data: bytes, content_type: str) -> StoredObject:
        digest = hashlib.sha256(data).hexdigest()
        try:
            existing = self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") not in {"404", "NoSuchKey", "NotFound"}:
                raise
        else:
            if existing.get("Metadata", {}).get("sha256") != digest:
                raise ValueError("immutable object key already contains different bytes")
            return StoredObject(key, digest, len(data))
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=BytesIO(data),
            ContentLength=len(data),
            ContentType=content_type,
            Metadata={"sha256": digest},
        )
        return StoredObject(key, digest, len(data))

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def signed_download_url(self, key: str, *, expires_seconds: int = 300) -> str:
        return self.public_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )

    def list_keys(self, prefix: str = "") -> list[str]:
        keys: list[str] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(item["Key"] for item in page.get("Contents", []))
        return keys

    def download_to(self, key: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, key, str(destination))

    def ping(self) -> bool:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True
        except Exception:
            return False
