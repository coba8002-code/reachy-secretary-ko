"""Face enrollment and recognition.

Everything stays on this machine. Enrolled people are stored as embeddings -
512 floats per face - not as photos, and nothing is uploaded anywhere.

Recognition uses InsightFace (buffalo_l). Embeddings are L2-normalised, so
cosine similarity is a plain dot product and lives in [-1, 1].
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

STORE_PATH = Path(
    os.getenv("REACHY_FACES_STORE", Path.home() / ".local" / "share" / "reachy-secretary" / "faces.json")
)

# Cosine similarity above this counts as the same person. InsightFace's own
# guidance puts the same/different boundary near 0.4 for buffalo_l; 0.45 trades
# a few more "who is that?" moments for far fewer wrong names, which is the
# right way round for something that announces intruders.
MATCH_THRESHOLD = float(os.getenv("REACHY_FACE_THRESHOLD", "0.45"))
# Faces smaller than this many pixels wide are too far away to trust.
MIN_FACE_WIDTH = int(os.getenv("REACHY_MIN_FACE_WIDTH", "60"))

_analyzer = None


@dataclass
class Detection:
    """One face found in a frame."""

    name: str | None      # None means nobody enrolled matched
    score: float          # best cosine similarity against the roster
    bbox: tuple[int, int, int, int]
    embedding: np.ndarray

    @property
    def is_known(self) -> bool:
        """True when this face matched an enrolled person."""
        return self.name is not None


def analyzer():
    """Return the shared InsightFace model, loading it on first use.

    The first call downloads the model (a few hundred MB) and takes a while;
    later calls are instant.
    """
    global _analyzer
    if _analyzer is None:
        from insightface.app import FaceAnalysis

        _analyzer = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _analyzer.prepare(ctx_id=0, det_size=(640, 640))
    return _analyzer


def _load() -> dict[str, list[list[float]]]:
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(store: dict[str, list[list[float]]]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")


def roster() -> list[tuple[str, int]]:
    """Return (name, number of enrolled photos) for everyone on file."""
    return [(name, len(vectors)) for name, vectors in _load().items()]


def embed_image(path: Path) -> np.ndarray | None:
    """Return the embedding of the largest face in an image, or None."""
    import cv2

    image = cv2.imread(str(path))
    if image is None:
        return None

    faces = analyzer().get(image)
    if not faces:
        return None

    # A photo may catch bystanders; the subject is the biggest face.
    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    vector = np.asarray(face.normed_embedding, dtype=np.float32)
    return vector


def enroll(name: str, image_paths: list[Path]) -> tuple[int, list[str]]:
    """Add a person from photos. Returns (accepted count, skipped filenames)."""
    store = _load()
    vectors = store.get(name, [])
    skipped: list[str] = []

    for path in image_paths:
        vector = embed_image(path)
        if vector is None:
            skipped.append(path.name)
            continue
        vectors.append(vector.tolist())

    store[name] = vectors
    _save(store)
    return len(vectors), skipped


def forget(name: str) -> bool:
    """Remove a person. Returns True if they were on file."""
    store = _load()
    if name not in store:
        return False
    del store[name]
    _save(store)
    return True


def _matrix() -> tuple[list[str], np.ndarray]:
    """Return the roster as parallel (names, embeddings) arrays."""
    names: list[str] = []
    rows: list[list[float]] = []
    for name, vectors in _load().items():
        for vector in vectors:
            names.append(name)
            rows.append(vector)
    if not rows:
        return [], np.zeros((0, 512), dtype=np.float32)
    return names, np.asarray(rows, dtype=np.float32)


def identify(frame: np.ndarray) -> list[Detection]:
    """Find every face in a frame and name the ones we recognise."""
    faces = analyzer().get(frame)
    if not faces:
        return []

    names, known = _matrix()
    results: list[Detection] = []

    for face in faces:
        x1, y1, x2, y2 = (int(v) for v in face.bbox)
        if (x2 - x1) < MIN_FACE_WIDTH:
            continue  # too far away to judge

        vector = np.asarray(face.normed_embedding, dtype=np.float32)
        name, score = None, 0.0

        if len(known):
            # Embeddings are L2-normalised, so the dot product is the cosine.
            sims = known @ vector
            best = int(np.argmax(sims))
            score = float(sims[best])
            if score >= MATCH_THRESHOLD:
                name = names[best]

        results.append(Detection(name=name, score=score, bbox=(x1, y1, x2, y2), embedding=vector))

    return results
