from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class Action(str, Enum):
    ASK = "ASK"
    CLARIFY = "CLARIFY"
    RECOMMEND = "RECOMMEND"
    END_NOT_US = "END_NOT_US"


class Question(BaseModel):
    id: str = Field(..., description="Dot-path where the answer should be stored")
    text: str
    answer_type: Literal["text", "number", "choice", "multi_choice"]
    options: List[str] = Field(default_factory=list)


class PatchOp(BaseModel):
    path: str

    # Must be JSON-schema representable for OpenAI structured outputs.
    value: Union[
        str,
        int,
        float,
        bool,
        None,
        List[str],
        List[int],
        List[float],
        List[bool],
        Dict[str, str],
        Dict[str, int],
        Dict[str, float],
        Dict[str, bool],
        Dict[str, None],
    ]


class Scholarship(BaseModel):
    name: str = Field(..., minLength=1)
    college: Optional[str] = Field(
        None,
        description="If this is an institutional scholarship, the target college/university name.",
    )
    kind: Literal["institutional", "external", "need_based_aid"] = "external"
    provider: Optional[str] = None
    award: Optional[str] = Field(None, description="Award amount/range as shown on the official page")
    deadline: Optional[str] = Field(
        None,
        description="Application deadline in ISO format YYYY-MM-DD when available; otherwise null.",
    )
    link: str = Field(..., description="Official scholarship page URL")

    why_suitable: str = Field(..., description="Why it fits this student")
    key_eligibility: List[str] = Field(default_factory=list)
    how_to_apply: List[str] = Field(default_factory=list)


class NextTurn(BaseModel):
    action: Action
    question: Optional[Question] = None
    profile_patch: List[PatchOp] = Field(default_factory=list)
    note_to_user: str = ""
    recommendations: Optional[List[Scholarship]] = None


# Schema for tool-enforced JSON outputs if you later switch this node to
# use the Responses API with json_schema.
NEXT_TURN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {"type": "string", "enum": ["ASK", "CLARIFY", "RECOMMEND", "END_NOT_US"]},
        "question": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "id": {"type": "string"},
                "text": {"type": "string", "minLength": 1},
                "answer_type": {"type": "string", "enum": ["text", "number", "choice", "multi_choice"]},
                "options": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["id", "text", "answer_type", "options"],
        },
        "profile_patch": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "value": {
                        "anyOf": [
                            {"type": "string"},
                            {"type": "number"},
                            {"type": "boolean"},
                            {"type": "null"},
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "array", "items": {"type": "number"}},
                        ]
                    },
                },
                "required": ["path", "value"],
            },
            "maxItems": 12,
        },
        "note_to_user": {"type": "string"},
        "recommendations": {
            "type": ["array", "null"],
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "college": {"type": ["string", "null"]},
                    "kind": {"type": "string", "enum": ["institutional", "external", "need_based_aid"]},
                    "provider": {"type": ["string", "null"]},
                    "award": {"type": ["string", "null"]},
                    "deadline": {
                        "type": ["string", "null"],
                        "description": "ISO date YYYY-MM-DD when available",
                        "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                    },
                    "link": {"type": "string", "minLength": 1},
                    "why_suitable": {"type": "string"},
                    "key_eligibility": {"type": "array", "items": {"type": "string"}},
                    "how_to_apply": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "kind", "link", "why_suitable", "key_eligibility", "how_to_apply"],
            },
        },
    },
    "required": ["action", "question", "profile_patch", "note_to_user", "recommendations"],
}
