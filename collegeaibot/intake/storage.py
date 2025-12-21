"""Simple profile storage backends for the intake agent.

For now we support in-memory and JSON-file-backed storage. The interface
is deliberately minimal so that a MongoDB-backed implementation can be
added later without changing the agent logic.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Protocol

from .agent import apply_patch_ops, new_profile


class ProfileStore(Protocol):
    """Minimal interface expected by downstream orchestration code."""

    def get_profile(self, client_id: str) -> Dict[str, Any]:  # pragma: no cover - interface only
        ...

    def update_profile(self, client_id: str, profile_patch: List[Dict[str, Any]]) -> Dict[str, Any]:  # pragma: no cover - interface only
        ...


class InMemoryProfileStore:
    """Volatile store, useful for tests or ephemeral sessions."""

    def __init__(self) -> None:
        self._profiles: Dict[str, Dict[str, Any]] = {}

    def get_profile(self, client_id: str) -> Dict[str, Any]:
        if client_id not in self._profiles:
            self._profiles[client_id] = new_profile()
        return self._profiles[client_id]

    def update_profile(self, client_id: str, profile_patch: List[Dict[str, Any]]) -> Dict[str, Any]:
        profile = self.get_profile(client_id)
        apply_patch_ops(profile, profile_patch)
        return profile


class JsonFileProfileStore:
    """Very simple JSON-file-backed profile store.

    The on-disk format is a single JSON object mapping ``client_id`` to
    its profile dict. This is intentionally naive but makes it easy to
    inspect and backfill data before moving to MongoDB.
    """

    def __init__(self, path: str | os.PathLike = "data/intake_profiles.json") -> None:
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
        if client_id not in data:
            data[client_id] = new_profile()
            self._save_all(data)
        return data[client_id]

    def update_profile(self, client_id: str, profile_patch: List[Dict[str, Any]]) -> Dict[str, Any]:
        data = self._load_all()
        profile = data.get(client_id) or new_profile()
        apply_patch_ops(profile, profile_patch)
        data[client_id] = profile
        self._save_all(data)
        return profile
