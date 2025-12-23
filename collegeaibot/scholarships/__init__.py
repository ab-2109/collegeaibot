"""Scholarships recommendation node.

Uses the student's intake profile and (optionally) asks a small number of
follow-up questions, then produces actionable scholarship search leads.
"""

from .agent import ScholarshipsAgent

__all__ = ["ScholarshipsAgent"]
