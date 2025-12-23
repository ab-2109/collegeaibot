"""Pydantic schemas for the scholarship prep agent."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class Action(str, Enum):
    ASK = "ASK"
    CLARIFY = "CLARIFY"
    SUGGEST = "SUGGEST"
    END = "END"


class Question(BaseModel):
    """A question to ask the student to understand their current profile better."""

    id: str = Field(..., description="Dot-path where the answer should be stored in the profile (e.g., 'prep.current_activities')")
    text: str = Field(..., description="The question text to display to the user")
    answer_type: Literal["text", "number", "choice", "multi_choice"] = "text"
    options: List[str] = Field(default_factory=list, description="Options for choice/multi_choice questions")


class PatchOp(BaseModel):
    """A patch operation to update the student's profile."""

    path: str = Field(..., description="Dot-path in the profile to update")
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
    ] = Field(..., description="The value to set at the path")


class Suggestion(BaseModel):
    """A concrete suggestion to improve scholarship chances."""

    title: str = Field(..., description="Short title for the suggestion (e.g., 'Apply to Google CSSI')")
    category: Literal[
        "internship",
        "program",
        "competition",
        "volunteer",
        "course",
        "certification",
        "leadership",
        "research",
        "skill_building",
        "application_tip",
        "essay_strategy",
        "networking",
        "other",
    ] = Field(..., description="Category of the suggestion")

    description: str = Field(..., description="Detailed description of what this is and why it helps")
    target_scholarships: List[str] = Field(
        default_factory=list,
        description="Which scholarships from the list this suggestion specifically helps with",
    )

    link: Optional[str] = Field(None, description="Official URL for the program/opportunity if available")
    deadline: Optional[str] = Field(None, description="Deadline in ISO format YYYY-MM-DD if applicable")
    estimated_time: Optional[str] = Field(None, description="Estimated time commitment (e.g., '2-3 months', '10 hours/week')")

    priority: Literal["high", "medium", "low"] = Field(
        "medium",
        description="Priority level based on impact and feasibility",
    )
    difficulty: Literal["easy", "moderate", "challenging"] = Field(
        "moderate",
        description="How difficult this is to accomplish",
    )

    action_steps: List[str] = Field(
        default_factory=list,
        description="Concrete next steps to take",
    )


class NextTurn(BaseModel):
    """Response from the scholarship prep agent for a single turn."""

    action: Action = Field(..., description="The action type for this turn")

    question: Optional[Question] = Field(
        None,
        description="Question to ask (when action=ASK)",
    )

    profile_patch: List[PatchOp] = Field(
        default_factory=list,
        description="Profile updates to apply based on the user's answer",
    )

    note_to_user: str = Field(
        "",
        description="A brief note or explanation to show the user",
    )

    suggestions: Optional[List[Suggestion]] = Field(
        None,
        description="List of suggestions (when action=SUGGEST)",
    )

    summary: Optional[str] = Field(
        None,
        description="Overall summary of recommendations and strategy",
    )
