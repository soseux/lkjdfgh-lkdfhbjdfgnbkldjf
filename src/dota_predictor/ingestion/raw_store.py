from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class StoredObject:
    path: Path
    sha256: str
    size_bytes: int


class RawStore:
    """Content-addressed local storage for untouched API responses."""

    _SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9_.=-]+")

    def __init__(self, root: Path) -> None:
        self.root = root

    @classmethod
    def _safe(cls, value: str) -> str:
        sanitized = cls._SAFE_COMPONENT.sub("_", value).strip("._")
        return sanitized or "unknown"

    def write_json(
        self,
        *,
        source: str,
        object_type: str,
        natural_key: str,
        data: Any,
    ) -> StoredObject:
        payload = json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        directory = (
            self.root / self._safe(source) / self._safe(object_type) / self._safe(natural_key)
        )
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{digest}.json"
        if not destination.exists():
            temporary = directory / f".{digest}.{os.getpid()}.tmp"
            temporary.write_bytes(payload)
            os.replace(temporary, destination)
        return StoredObject(path=destination, sha256=digest, size_bytes=len(payload))
