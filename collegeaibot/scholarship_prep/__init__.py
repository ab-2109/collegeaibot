"""Scholarship preparation agent - suggests programs, internships, and improvements
to increase chances for recommended scholarships."""

from .agent import ScholarshipPrepAgent, ScholarshipPrepConfig
from .schemas import Action, NextTurn, Suggestion, Question, PatchOp

__all__ = [
    "ScholarshipPrepAgent",
    "ScholarshipPrepConfig",
    "Action",
    "NextTurn",
    "Suggestion",
    "Question",
    "PatchOp",
]
