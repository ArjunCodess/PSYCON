"""Install pinned public ONNX models during image build, never during a request."""

import hashlib
import io
import tarfile
import urllib.request

from .diarization import model_directory


RELEASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
ASSETS = (
    ("speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
     "24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488", "segmentation.onnx"),
    ("speaker-recongition-models/nemo_en_titanet_small.onnx",
     "ad4a1802485d8b34c722d2a9d04249662f2ece5d28a7a039063ca22f515a789e", "embedding.onnx"),
)


def main():
    destination = model_directory()
    destination.mkdir(parents=True, exist_ok=True)
    for asset, expected, name in ASSETS:
        with urllib.request.urlopen(RELEASE + asset, timeout=120) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError(f"model checksum mismatch: {name}")
        if asset.endswith(".tar.bz2"):
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:bz2") as archive:
                # Read only named members; never extract arbitrary archive paths.
                root = "sherpa-onnx-pyannote-segmentation-3-0/"
                data = archive.extractfile(root + "model.onnx").read()
                (destination / "segmentation-LICENSE").write_bytes(archive.extractfile(root + "LICENSE").read())
        (destination / name).write_bytes(data)


if __name__ == "__main__":
    main()
