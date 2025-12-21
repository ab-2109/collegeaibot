"""Intake/questionnaire agent for collecting structured applicant profiles.

The core entrypoint is :class:`IntakeAgent`, which:
- Maintains no internal state (profile is passed in and patched).
- Calls the OpenAI Responses API with a strict JSON schema for outputs.
- Returns the next question + profile_patch for the caller to merge/store.

This module is designed so IntakeAgent can be used as a node in a
LangGraph graph later: the `profile` dict can be part of the graph state,
while `last_user_answer` comes from the previous step in the workflow.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .client import DEFAULT_MODEL, get_openai_client
from .prompts import SYSTEM_INSTRUCTIONS
from .schemas import DEEP_PATHS_ORDER, NEXT_TURN_SCHEMA, PROFILE_TEMPLATE, PRIORITY_SLOTS


def deep_merge(dst: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge ``patch`` into ``dst`` and return ``dst``."""
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            deep_merge(dst[key], value)
        else:
            dst[key] = value
    return dst


def set_by_path(dst: Dict[str, Any], path: str, value: Any) -> None:
    """Set a nested value on a dict using dot-separated paths.

    Example: set_by_path(profile, "sat.status", "Taken")
    """

    cur: Any = dst
    parts = [p for p in path.split(".") if p]
    if not parts:
        return

    for key in parts[:-1]:
        if not isinstance(cur, dict):
            return
        if key not in cur or not isinstance(cur.get(key), dict):
            cur[key] = {}
        cur = cur[key]

    if isinstance(cur, dict):
        cur[parts[-1]] = value


def apply_patch_ops(dst: Dict[str, Any], ops: List[Dict[str, Any]]) -> None:
    """Apply a list of patch operations of shape {path, value}."""

    for op in ops or []:
        if not isinstance(op, dict):
            continue
        path = op.get("path")
        if not isinstance(path, str) or not path.strip():
            continue
        set_by_path(dst, path.strip(), op.get("value"))


def _is_answered(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        # Treat "Not sure" / "Skip" / "Prefer not to say" as answered to avoid loops.
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return any(_is_answered(v) for v in value.values())
    return True


def _get_by_path(d: Dict[str, Any], path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


@dataclass(frozen=True)
class IntakeConfig:
    """Controls how far the intake should go before finishing."""

    completion_mode: str = "deep"  # "deep" | "core"
    max_output_tokens: int = 700


def _extract_first_message_text(resp: Any) -> str:
    """
    Avoid resp.output_text (can concatenate multiple chunks/items).
    Pull the first assistant message text chunk deterministically.
    """
    # Prefer the SDK helper; with strict JSON schema outputs this should be
    # a single JSON object and is the most stable across SDK versions.
    t = getattr(resp, "output_text", None)
    if isinstance(t, str) and t.strip():
        return t.strip()

    # Otherwise, walk the raw output structure. Depending on SDK version,
    # items may be objects or plain dicts.
    output = getattr(resp, "output", None)
    if output is None and isinstance(resp, dict):
        output = resp.get("output")

    for item in output or []:
        item_type = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
        if item_type != "message":
            continue

        content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
        for c in content or []:
            c_type = c.get("type") if isinstance(c, dict) else getattr(c, "type", None)
            if c_type not in ("output_text", "text"):
                continue
            text = c.get("text") if isinstance(c, dict) else getattr(c, "text", None)
            if isinstance(text, str) and text.strip():
                return text.strip()

    return ""


def _parse_strict_json_object(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Empty model output (expected JSON).")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: try to salvage the first {...} block if extra text leaked in.
        start = raw.find("{")
        end = raw.rfind("}")
        if 0 <= start < end:
            candidate = raw[start : end + 1]
            return json.loads(candidate)
        raise


class IntakeAgent:
    """Thin wrapper around the OpenAI Responses API for intake turns."""

    def __init__(
        self,
        model: Optional[str] = None,
        client: Any = None,
        config: Optional[IntakeConfig] = None,
    ) -> None:
        self.model = model or DEFAULT_MODEL
        self.client = client or get_openai_client()
        self.config = config or IntakeConfig()

    def next_turn(
        self,
        profile: Dict[str, Any],
        last_user_answer: Optional[str],
        last_question_id: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        # Track which paths have already been asked (even if user answered "Skip").
        meta = profile.get("_meta") if isinstance(profile.get("_meta"), dict) else {}
        asked_paths = meta.get("asked_paths") if isinstance(meta.get("asked_paths"), list) else []
        asked_set = {p for p in asked_paths if isinstance(p, str) and p.strip()}

        unfilled_priority = [p for p in PRIORITY_SLOTS if not _is_answered(_get_by_path(profile, p))]
        filled_priority = [p for p in PRIORITY_SLOTS if p not in unfilled_priority]

        # Deep mode: keep going until we've covered the full path list.
        unfilled_deep_paths = []
        if self.config.completion_mode == "deep":
            for p in DEEP_PATHS_ORDER:
                if p in asked_set:
                    continue
                if _is_answered(_get_by_path(profile, p)):
                    continue
                unfilled_deep_paths.append(p)

        allow_finish = True
        if self.config.completion_mode == "deep" and unfilled_deep_paths:
            allow_finish = False

        input_messages = [
            {"role": "developer", "content": f"Current profile JSON:\n{json.dumps(profile, ensure_ascii=False)}"},
            {
                "role": "developer",
                "content": json.dumps(
                    {
                        "filled_priority_slots": filled_priority,
                        "unfilled_priority_slots": unfilled_priority,
                        "completion_mode": self.config.completion_mode,
                        "unfilled_deep_paths": unfilled_deep_paths,
                        "last_question_id": last_question_id,
                        "instruction": (
                            "Ask the earliest unfilled_priority_slot next. "
                            "Do NOT re-ask filled fields unless clarifying the immediately previous answer."
                        ),
                        "finish_policy": (
                            "FINISH is allowed." if allow_finish else "Do NOT FINISH yet; ask the next unfilled_deep_paths item."
                        ),
                    },
                    ensure_ascii=False,
                ),
            },
            {
                "role": "user",
                "content": (
                    "Start the intake interview. Ask the first question."
                    if last_user_answer is None
                    else f"User answered: {last_user_answer}"
                ),
            },
        ]

        resp = self.client.responses.create(
            model=self.model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=input_messages,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "college_intake_next_turn",
                    "strict": True,
                    "schema": NEXT_TURN_SCHEMA,
                }
            },
            max_output_tokens=self.config.max_output_tokens,
            store=False,
        )

        raw = _extract_first_message_text(resp)
        try:
            data = _parse_strict_json_object(raw)
        except Exception as e:
            # Make the failure actionable
            snippet = raw[:1200].replace("\n", "\\n")
            raise RuntimeError(f"Failed to parse model JSON. Raw snippet: {snippet}") from e

        patch_ops = data.get("profile_patch") or []
        updated_profile = copy.deepcopy(profile)
        if isinstance(patch_ops, list):
            apply_patch_ops(updated_profile, patch_ops)

        # Record that we asked this path (prevents re-asking on Skip/Not sure).
        if last_question_id and isinstance(last_question_id, str) and last_question_id.strip() and last_user_answer is not None:
            meta2 = updated_profile.get("_meta") if isinstance(updated_profile.get("_meta"), dict) else {}
            asked2 = meta2.get("asked_paths") if isinstance(meta2.get("asked_paths"), list) else []
            if last_question_id.strip() not in asked2:
                asked2.append(last_question_id.strip())
            meta2["asked_paths"] = asked2
            updated_profile["_meta"] = meta2

        # If the model tries to finish early in deep mode, ask again once.
        if self.config.completion_mode == "deep" and data.get("action") == "FINISH":
            # Recompute against the updated profile.
            meta_u = updated_profile.get("_meta") if isinstance(updated_profile.get("_meta"), dict) else {}
            asked_u = meta_u.get("asked_paths") if isinstance(meta_u.get("asked_paths"), list) else []
            asked_u_set = {p for p in asked_u if isinstance(p, str) and p.strip()}
            remaining = [
                p for p in DEEP_PATHS_ORDER
                if p not in asked_u_set and not _is_answered(_get_by_path(updated_profile, p))
            ]
            if remaining:
                # Force another turn that asks about the next remaining path.
                forced_next = remaining[0]
                forced_messages = input_messages[:-1] + [
                    {
                        "role": "developer",
                        "content": (
                            f"DO NOT FINISH. Ask about this exact field path next: {forced_next}. "
                            "Set question.id to that path."
                        ),
                    },
                    input_messages[-1],
                ]

                resp2 = self.client.responses.create(
                    model=self.model,
                    instructions=SYSTEM_INSTRUCTIONS,
                    input=forced_messages,
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "college_intake_next_turn",
                            "strict": True,
                            "schema": NEXT_TURN_SCHEMA,
                        }
                    },
                    max_output_tokens=self.config.max_output_tokens,
                    store=False,
                )
                raw2 = _extract_first_message_text(resp2)
                data2 = _parse_strict_json_object(raw2)
                patch_ops2 = data2.get("profile_patch") or []
                if isinstance(patch_ops2, list):
                    apply_patch_ops(updated_profile, patch_ops2)
                return data2, updated_profile

        return data, updated_profile


def new_profile() -> Dict[str, Any]:
    """Return a fresh, independent copy of the base profile template."""
    return copy.deepcopy(PROFILE_TEMPLATE)
