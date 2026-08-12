from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from functools import wraps
from typing import Callable
from uuid import uuid4

from flask import current_app, g, jsonify, request


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_token() -> str:
    return secrets.token_urlsafe(32)


@dataclass(frozen=True)
class Principal:
    id: str
    role: str
    device_id: int | None
    label: str


def bootstrap_operator(database, token: str) -> None:
    digest = hash_token(token)
    with database.connection() as connection:
        connection.execute(
            """
            INSERT INTO credentials(id, label, role, token_hash)
            VALUES (%s, 'local bootstrap operator', 'operator', %s)
            ON CONFLICT(token_hash) DO NOTHING
            """,
            (uuid4(), digest),
        )


def authenticate(database, token: str) -> Principal | None:
    supplied = hash_token(token)
    with database.connection() as connection:
        rows = connection.execute(
            "SELECT id, role, device_id, label, token_hash FROM credentials WHERE revoked_at IS NULL"
        ).fetchall()
    for row in rows:
        if hmac.compare_digest(row["token_hash"], supplied):
            return Principal(str(row["id"]), row["role"], row["device_id"], row["label"])
    return None


def require_role(*roles: str) -> Callable:
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            token = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
            principal = authenticate(current_app.extensions["psycon_db"], token) if token else None
            if principal is None or principal.role not in roles:
                return jsonify({"status": "error", "error": {"code": "unauthorized", "message": "Valid credentials are required"}}), 401
            g.principal = principal
            return view(*args, **kwargs)
        return wrapped
    return decorator
