"""Standalone audio-only app, with no hardware, PostgreSQL, or object-store prerequisite."""
from pathlib import Path

from flask import Flask, jsonify, render_template
from werkzeug.exceptions import RequestEntityTooLarge

from . import DEFINITION
from .routes import api, pages
from .service import Instrument


def create_app(root="instance/instrument", instrument=None, testing=False):
    backend = Path(__file__).resolve().parents[1]
    app = Flask(__name__, template_folder=str(backend/"templates"), static_folder=str(backend/"static"))
    app.config.update(TESTING=testing, MAX_CONTENT_LENGTH=1024*1024*1024, PSYCON_DEFINITION=DEFINITION)
    app.extensions["psycon_instrument"] = instrument or Instrument(root)
    app.register_blueprint(api)
    app.register_blueprint(pages)

    @app.get("/")
    def home():
        return render_template("instrument.html")

    @app.get("/health")
    def health():
        return jsonify(status="ok", mode="audio-only research instrument")

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(exc):
        return jsonify(error="Request exceeds 1 GiB. Upload fewer recordings at once; each recording is limited to 512 MiB."), 413

    @app.after_request
    def secure(response):
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; media-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response
    return app
