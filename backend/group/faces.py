"""Mark faces on the first usable frame and number them from the right.

Participant numbers are positions in this recording. They are not names, and a
face crop is not an identity that follows a person into another session.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np


FEATURE_SIZE = 80
_SAMPLE_SECONDS = (0.0, 1.0, 5.0)


class FaceMarkError(ValueError):
    pass


def mark_recording(data: bytes) -> dict:
    """Return a JPEG of the first frame that shows at least two faces.

    The search tries the opening frame, then one second, then five seconds.
    The last decoded frame is returned when fewer than two faces are found.
    """
    fallback = None
    for second in _SAMPLE_SECONDS:
        frame = read_frame_at(data, second)
        if frame is None:
            continue
        faces = detect_faces(frame)
        rendered = draw_marks(frame, faces)
        candidate = {"jpeg": rendered, "faces": faces, "time_s": second}
        fallback = candidate
        if len(faces) >= 2:
            return candidate
    if fallback is None:
        raise FaceMarkError("The first frame could not be read from this video")
    return fallback


def read_frame_at(data: bytes, second: float) -> np.ndarray | None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FaceMarkError("ffmpeg is required to read the first frame")
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source.mp4"
        target = Path(directory) / "frame.jpg"
        source.write_bytes(data)
        completed = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-ss",
                f"{second:.3f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(target),
            ],
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0 or not target.exists() or target.stat().st_size == 0:
            return None
        return decode_image(target.read_bytes())


def decode_image(blob: bytes) -> np.ndarray | None:
    import cv2

    image = cv2.imdecode(np.frombuffer(blob, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return None
    return image


def detect_faces(image: np.ndarray) -> list[dict]:
    import cv2

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    height, width = gray.shape[:2]
    minimum = max(28, width // 30)
    boxes: list[tuple[int, int, int, int]] = []
    for name in ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml", "haarcascade_profileface.xml"):
        cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / name))
        found = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=(minimum, minimum))
        boxes.extend((int(x), int(y), int(w), int(h)) for x, y, w, h in found)
    kept = _suppress(boxes)
    normalized = []
    for x, y, w, h in kept:
        box = (x / width, y / height, w / width, h / height)
        normalized.append(
            {
                "x": box[0],
                "y": box[1],
                "width": box[2],
                "height": box[3],
                "feature": face_feature(image, box),
            }
        )
    return number_faces(normalized)


def number_faces(faces: list[dict]) -> list[dict]:
    """Participant 1 is the face on the right of the displayed frame."""
    ordered = sorted(faces, key=lambda face: -((float(face["x"]) + float(face["width"]) / 2)))
    numbered = []
    for index, face in enumerate(ordered, start=1):
        numbered.append({**face, "slot_number": index, "label": f"Participant {index}"})
    return numbered


def face_feature(image: np.ndarray, box: tuple[float, float, float, float]) -> list[float]:
    """Fixed-length appearance vector for one face crop. It is not an identity."""
    height, width = image.shape[:2]
    x0 = max(0, min(width - 1, int(box[0] * width)))
    y0 = max(0, min(height - 1, int(box[1] * height)))
    x1 = max(x0 + 1, min(width, int((box[0] + box[2]) * width)))
    y1 = max(y0 + 1, min(height, int((box[1] + box[3]) * height)))
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return [0.0] * FEATURE_SIZE
    gray = crop.mean(axis=2) if crop.ndim == 3 else crop.astype(np.float64)
    grid = _block_means(gray, 8)
    flat = grid.reshape(-1)
    centered = flat - float(flat.mean())
    scale = float(np.sqrt(np.mean(centered**2))) or 1.0
    pixels = (centered / scale).tolist()
    gradients = _gradient_bins(grid)
    return pixels + gradients


def draw_marks(image: np.ndarray, faces: list[dict]) -> bytes:
    import cv2

    canvas = image.copy()
    height, width = canvas.shape[:2]
    for face in faces:
        x0 = int(face["x"] * width)
        y0 = int(face["y"] * height)
        x1 = int((face["x"] + face["width"]) * width)
        y1 = int((face["y"] + face["height"]) * height)
        cv2.rectangle(canvas, (x0, y0), (x1, y1), (36, 118, 107), 2)
        label = str(face["slot_number"])
        origin = (x0, max(18, y0 - 6))
        cv2.rectangle(canvas, (origin[0], origin[1] - 16), (origin[0] + 18, origin[1] + 4), (36, 118, 107), -1)
        cv2.putText(canvas, label, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise FaceMarkError("The marked frame could not be encoded")
    return encoded.tobytes()


def _suppress(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    ordered = sorted(boxes, key=lambda box: box[2] * box[3], reverse=True)
    kept: list[tuple[int, int, int, int]] = []
    for box in ordered:
        if all(_iou(box, other) < 0.35 for other in kept):
            kept.append(box)
    return kept


def _iou(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = left
    bx, by, bw, bh = right
    x0 = max(ax, bx)
    y0 = max(ay, by)
    x1 = min(ax + aw, bx + bw)
    y1 = min(ay + ah, by + bh)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    overlap = (x1 - x0) * (y1 - y0)
    union = aw * ah + bw * bh - overlap
    return overlap / union if union else 0.0


def _block_means(gray: np.ndarray, size: int) -> np.ndarray:
    height, width = gray.shape[:2]
    grid = np.zeros((size, size), dtype=np.float64)
    for row in range(size):
        y0 = int(row * height / size)
        y1 = max(y0 + 1, int((row + 1) * height / size))
        for column in range(size):
            x0 = int(column * width / size)
            x1 = max(x0 + 1, int((column + 1) * width / size))
            grid[row, column] = float(gray[y0:y1, x0:x1].mean())
    return grid


def _gradient_bins(grid: np.ndarray) -> list[float]:
    horizontal = np.diff(grid, axis=1).reshape(-1)
    vertical = np.diff(grid, axis=0).reshape(-1)
    return _histogram(horizontal) + _histogram(vertical)


def _histogram(values: np.ndarray) -> list[float]:
    if values.size == 0:
        return [0.0] * 8
    clipped = np.clip(values, -2.0, 2.0)
    counts, _edges = np.histogram(clipped, bins=8, range=(-2.0, 2.0))
    total = float(counts.sum()) or 1.0
    return (counts / total).astype(float).tolist()
