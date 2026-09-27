"""Stream video frames for a repeatable inventory and marked review screenshots."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.group.faces import add_identity_vectors, detect_faces, draw_marks, rotate_frame


SOURCE = Path("group_discussions")
OUTPUT = Path("instance/group_batch")
OUTPUT.mkdir(parents=True, exist_ok=True)


def sampled_frame(capture, second):
    capture.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
    ok, frame = capture.read()
    return frame if ok else None


def inventory(path):
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return {"file": path.name, "status": "video_decode_failed"}
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = frames / fps if fps else 0.
        best = None
        samples = []
        for second in (0., 1., 5., 10., 20.):
            frame = sampled_frame(capture, second)
            if frame is None:
                continue
            choices = []
            for angle in (0, 90, 180, 270):
                upright = rotate_frame(frame, angle)
                found = detect_faces(upright)
                choices.append((len(found), sum(face["detection_score"] for face in found),
                                angle, upright, found))
            chosen = max(choices, key=lambda item: item[:2])
            samples.append({"second": second, "detected_faces": chosen[0],
                            "rotation_degrees": chosen[2]})
            if best is None or chosen[:2] > best[0][:2]:
                best = (chosen, second)
        if best is None:
            return {"file": path.name, "status": "no_frames", "duration_s": duration}
        (count, _confidence, rotation, image, faces), second = best
        faces = add_identity_vectors(image, faces)
        screenshot = OUTPUT / f"{path.stem}-marked.jpg"
        screenshot.write_bytes(draw_marks(image, faces))
        return {"file": path.name, "status": "complete", "bytes": path.stat().st_size,
                "duration_s": round(duration, 3), "fps": round(fps, 3),
                "width": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "marked_frame_s": second, "rotation_degrees": rotation,
                "detected_faces": count, "samples": samples,
                "screenshot": str(screenshot), "faces": faces}
    finally:
        capture.release()


if __name__ == "__main__":
    results = []
    for path in sorted(SOURCE.iterdir()):
        if path.suffix.lower() not in {".mov", ".mp4"} or path.stat().st_size == 0:
            continue
        result = inventory(path)
        results.append(result)
        (OUTPUT / "inventory.json").write_text(json.dumps(results, indent=2))
        print(path.name, result["status"], result.get("duration_s"),
              result.get("detected_faces"), flush=True)
