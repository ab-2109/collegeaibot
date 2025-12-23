"""Core package for the college AI bot.

This package currently exposes the intake/questionnaire agent, which is
intended to be used as a node in a larger agentic pipeline (e.g. LangGraph).
"""

from .intake.agent import IntakeAgent  # re-export for convenience
from .scholarships.agent import ScholarshipsAgent

__all__ = ["IntakeAgent", "ScholarshipsAgent"]
