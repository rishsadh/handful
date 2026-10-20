"""Content hashing.

Provenance for this project rests on hashes: the raw bytes we audited, the exact text we
embedded, and the config that produced a run. All of it is SHA-256.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_CHUNK = 1024 * 1024


def sha256_file(path: Path | str) -> str:
    """SHA-256 of a file's bytes, streamed so a 300 MB CSV does not land in memory."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    """SHA-256 of a string, encoded UTF-8. Used for rendered recipe text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_obj(obj: Any) -> str:
    """SHA-256 of a JSON-serialisable object with sorted keys.

    Deterministic across runs and platforms, which is what makes it usable as a config
    fingerprint in a run manifest.
    """
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_text(payload)


def short(digest: str, n: int = 12) -> str:
    return digest[:n]
