from __future__ import annotations

import atexit

from flask import Flask
from flask import jsonify
from werkzeug.exceptions import RequestEntityTooLarge

from .auth import bootstrap_operator
from .config import Settings
from .db import Database
from .inference import InferenceEngine
from .repository import Repository
from .routes import api, pages
from .services import ExportService, IngestionService, Processor
from .storage import ObjectStorage


def create_app(
    *,
    testing: bool = False,
    settings: Settings | None = None,
    database=None,
    storage=None,
    initialize: bool = True,
) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    settings = settings or Settings.from_env(testing=testing)
    app.config.update(TESTING=testing, MAX_CONTENT_LENGTH=settings.max_chunk_bytes)
    app.secret_key = settings.secret_key

    database = database or Database(settings.database_url)
    storage = storage or ObjectStorage(settings)
    if initialize:
        database.migrate()
        storage.ensure_bucket()
        bootstrap_operator(database, settings.bootstrap_operator_token)

    repository = Repository(database, max_sync_uncertainty_us=settings.sync_max_uncertainty_us)
    inference = InferenceEngine.from_path(settings.model_artifact_path)
    app.extensions.update(
        psycon_settings=settings,
        psycon_db=database,
        psycon_storage=storage,
        psycon_repository=repository,
        psycon_inference=inference,
        psycon_ingestion=IngestionService(repository, storage),
        psycon_processor=Processor(repository, storage, inference),
        psycon_exporter=ExportService(repository, storage),
    )
    app.register_blueprint(pages)
    app.register_blueprint(api)

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(_error):
        return jsonify({"status": "error", "error": {"code": "payload_too_large", "message": "Request exceeds the server limit"}}), 413

    @app.after_request
    def security_headers(response):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
            "style-src 'self' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; script-src 'self'; "
            "base-uri 'none'; frame-ancestors 'none'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if response.mimetype == "application/json":
            response.headers.setdefault("Cache-Control", "no-store")
        return response
    if hasattr(database, "close"):
        atexit.register(database.close)
    return app
