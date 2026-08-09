"""Local web interface for inspecting real WAV recordings with PSYCON."""

from __future__ import annotations

import argparse
import base64
import hashlib

from flask import Flask, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

from ml.src.audio_recording import AudioRecordingError, analyze_decoded_recording, decode_wav
from ml.src.language_features import extract_language_features
from ml.src.transcription import (
    FasterWhisperTranscriber,
    Transcriber,
    not_requested_transcription,
    transcribe_usable_regions,
)


MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def create_app(*, testing: bool = False, transcriber: Transcriber | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES, TESTING=testing)
    speech_transcriber = transcriber or FasterWhisperTranscriber()

    @app.route("/", methods=["GET", "POST"])
    def index():
        result = None
        error = None
        audio_data_url = None
        status_code = 200
        if request.method == "POST":
            upload = request.files.get("audio")
            if upload is None or not upload.filename:
                error = "Choose a WAV recording before running the analysis."
                status_code = 400
            elif request.form.get("consent") != "yes":
                error = "Confirm that you have permission to process this recording."
                status_code = 400
            else:
                source = upload.read()
                try:
                    decoded = decode_wav(source)
                    result = analyze_decoded_recording(
                        decoded,
                        upload.filename,
                        hashlib.sha256(source).hexdigest(),
                    )
                    if request.form.get("transcribe") == "yes":
                        transcription = transcribe_usable_regions(
                            decoded.samples,
                            decoded.sample_rate_hz,
                            result["windows"],
                            speech_transcriber,
                        )
                    else:
                        transcription = not_requested_transcription()
                    result["transcription"] = transcription.to_dict()
                    result["language_features"] = extract_language_features(transcription)
                    encoded = base64.b64encode(source).decode("ascii")
                    audio_data_url = f"data:audio/wav;base64,{encoded}"
                except AudioRecordingError as analysis_error:
                    error = str(analysis_error)
                    status_code = 400
        return render_template(
            "audio_upload.html",
            result=result,
            error=error,
            audio_data_url=audio_data_url,
            max_upload_mb=MAX_UPLOAD_BYTES // (1024 * 1024),
        ), status_code

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        return render_template(
            "audio_upload.html",
            result=None,
            error=f"The recording is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
            audio_data_url=None,
            max_upload_mb=MAX_UPLOAD_BYTES // (1024 * 1024),
        ), 413

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    create_app().run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
