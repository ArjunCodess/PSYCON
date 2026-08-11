"""Local web interface for inspecting real WAV recordings with PSYCON."""

from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path

from flask import Flask, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

from ml.src.audio_recording import AudioRecordingError, analyze_decoded_recording, decode_wav
from ml.src.language_features import extract_language_features
from ml.src.speaker_analysis import (
    Diarizer,
    PyannoteDiarizer,
    SpeakerEmbedder,
    SpeechBrainEmbedder,
    VoiceProfileStore,
    analyze_speakers,
    enroll_wearer,
    unavailable_speaker_analysis,
)
from ml.src.transcription import (
    FasterWhisperTranscriber,
    Transcriber,
    not_requested_transcription,
    transcribe_usable_regions,
)


MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def create_app(
    *,
    testing: bool = False,
    transcriber: Transcriber | None = None,
    diarizer: Diarizer | None = None,
    embedder: SpeakerEmbedder | None = None,
    profile_store: VoiceProfileStore | None = None,
) -> Flask:
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES, TESTING=testing)
    speech_transcriber = transcriber or FasterWhisperTranscriber()
    speaker_diarizer = diarizer or PyannoteDiarizer()
    speaker_embedder = embedder or SpeechBrainEmbedder()
    wearer_profiles = profile_store or VoiceProfileStore(
        Path(app.instance_path) / "wearer_profile.enc"
    )

    def profile_view() -> dict[str, object]:
        return {
            "configured": wearer_profiles.configured,
            "exists": wearer_profiles.exists,
        }

    @app.route("/", methods=["GET", "POST"])
    def index():
        result = None
        error = None
        audio_data_url = None
        status_code = 200
        message = request.args.get("message")
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
                    if request.form.get("speakers") == "yes":
                        if request.form.get("biometric_consent") != "yes":
                            result["speaker_analysis"] = unavailable_speaker_analysis(
                                "biometric_processing_consent_required"
                            )
                        else:
                            try:
                                profile = wearer_profiles.load()
                            except Exception as profile_error:
                                result["speaker_analysis"] = unavailable_speaker_analysis(
                                    f"profile_load_failed: {profile_error}"
                                )
                            else:
                                result["speaker_analysis"] = analyze_speakers(
                                    decoded.samples,
                                    decoded.sample_rate_hz,
                                    transcription,
                                    speaker_diarizer,
                                    speaker_embedder,
                                    profile,
                                )
                    else:
                        result["speaker_analysis"] = unavailable_speaker_analysis(
                            "speaker_analysis_not_requested"
                        )
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
            profile=profile_view(),
            message=message,
        ), status_code

    @app.post("/enroll")
    def enroll():
        if request.form.get("enrollment_consent") != "yes":
            return render_template(
                "audio_upload.html",
                result=None,
                error="Confirm consent before creating a biometric wearer profile.",
                audio_data_url=None,
                max_upload_mb=MAX_UPLOAD_BYTES // (1024 * 1024),
                profile=profile_view(),
                message=None,
            ), 400
        uploads = [request.files.get(f"enrollment_{number}") for number in range(1, 4)]
        if any(upload is None or not upload.filename for upload in uploads):
            error = "Choose all three enrollment WAV recordings."
        else:
            try:
                clips = []
                for upload in uploads:
                    decoded = decode_wav(upload.read())
                    clips.append((decoded.samples, decoded.sample_rate_hz))
                enroll_wearer(clips, speaker_embedder, wearer_profiles)
                return index_redirect("wearer profile saved")
            except (AudioRecordingError, ValueError, RuntimeError) as enrollment_error:
                error = str(enrollment_error)
            except Exception as enrollment_error:
                error = f"Enrollment failed: {type(enrollment_error).__name__}: {enrollment_error}"
        return render_template(
            "audio_upload.html",
            result=None,
            error=error,
            audio_data_url=None,
            max_upload_mb=MAX_UPLOAD_BYTES // (1024 * 1024),
            profile=profile_view(),
            message=None,
        ), 400

    @app.post("/profile/delete")
    def delete_profile():
        wearer_profiles.delete()
        return index_redirect("wearer profile deleted")

    def index_redirect(message: str):
        from flask import redirect, url_for

        return redirect(url_for("index", message=message))

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        return render_template(
            "audio_upload.html",
            result=None,
            error=f"The recording is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
            audio_data_url=None,
            max_upload_mb=MAX_UPLOAD_BYTES // (1024 * 1024),
            profile=profile_view(),
            message=None,
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
