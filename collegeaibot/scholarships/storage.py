from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Protocol

from ..intake.agent import apply_patch_ops


class ScholarshipStore(Protocol):
    def get_profile(self, client_id: str) -> Dict[str, Any]:  # pragma: no cover
        ...

    def update_profile(self, client_id: str, patch_ops: List[Dict[str, Any]]) -> Dict[str, Any]:  # pragma: no cover
        ...


class JsonFileScholarshipStore:
    """Stores scholarship-specific profile alongside the intake profile.

    For now we keep a single JSON mapping client_id -> profile dict.
    """

    def __init__(self, path: str | os.PathLike = "data/scholarships_profiles.json") -> None:
        self.path = Path(path)
        if not self.path.parent.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load_all(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save_all(self, data: Dict[str, Any]) -> None:
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)

    def get_profile(self, client_id: str) -> Dict[str, Any]:
        data = self._load_all()
        return data.get(client_id) or {}

    def update_profile(self, client_id: str, patch_ops: List[Dict[str, Any]]) -> Dict[str, Any]:
        data = self._load_all()
        profile = data.get(client_id) or {}
        apply_patch_ops(profile, patch_ops)
        data[client_id] = profile
        self._save_all(data)
        return profile
