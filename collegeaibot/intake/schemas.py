"""Schemas and templates for the intake/questionnaire agent.

These objects are kept Python-native (dicts/lists) so they can be reused
both in the OpenAI schema definition and in future backends
(e.g. MongoDB documents, LangGraph node state, etc.).
"""

from __future__ import annotations

PROFILE_TEMPLATE: dict = {
    # Internal metadata (safe to store alongside the profile)
    "_meta": {
        # Tracks which field paths have already been asked to avoid looping
        # even when the user answers "Not sure" / "Skip".
        "asked_paths": [],
    },

    # Gatekeeping
    "us_only": None,  # bool
    "residency_status": None,  # "US citizen" | "Permanent resident" | "DACA" | "Other"
    "state_of_residence": None,  # "CA", "Texas", etc.

    # Applicant type
    "applicant_type": None,  # "First-year" | "Transfer" | "CC transfer" | "Returning adult"
    "entry_term": None,  # e.g., "Fall 2026"
    "hs_grad_year": None,  # int (first-year track)
    "college_gpa": None,  # float/None (transfer track)

    # Academics snapshot
    "gpa_unweighted": None,  # float or "Not sure"
    "gpa_weighted": None,  # float or None
    "class_rank": None,  # {"has_rank": bool, "rank": int, "class_size": int} or None
    "highest_math": None,  # enum-ish
    "highest_science": None,  # enum-ish
    "rigor_tags": [],  # ["AP", "IB", "Dual Enrollment", "Honors"]

    # Testing
    "sat": {"status": None, "best_total": None, "ebrw": None, "math": None},
    "act": {"status": None, "best_composite": None},
    "test_strategy": None,  # "Submit if strong" | "Test-optional" | "Unsure"

    # Major & goals
    "intended_major_primary": None,
    "intended_major_alternates": [],
    "major_certainty": None,  # "Very sure" | "Somewhat" | "Exploring"
    "career_goal": None,  # text/tag
    "grad_school_plan": None,  # "Likely" | "Maybe" | "No" | "Unknown"

    # Preferences (fit)
    "regions_open_to": [],  # ["Northeast","Midwest","South","West"] or ["No preference"]
    "distance_preference": None,  # "Commute" | "Within X miles" | "Flight ok" | "No preference"
    "setting_preference": None,  # "Urban" | "Suburban" | "College town" | "Rural" | "No preference"
    "campus_size_pref": None,  # "Small" | "Medium" | "Large" | "No preference"
    "vibe_pref": None,  # "Party-heavy" | "Balanced" | "Quiet" | "No preference"

    # Budget & aid (ranges only)
    "budget_range_all_in": None,  # "<15k", "15-25k", ...
    "loan_tolerance": None,  # "$0", "<$5k/yr", "<$10k/yr", ...
    "in_state_importance": None,  # "Very" | "Somewhat" | "Not"
    "fafsa_intent": None,  # Yes/No/Not sure
    "css_profile_willing": None,  # Yes/No/Not sure

    # Constraints & dealbreakers
    "hard_dealbreakers": [],
    "soft_preferences": [],

    # Activities (optional deepening)
    "top_activities": [],  # list of dicts

    # Output preference
    "want_reach_match_safety": None,  # bool
    "list_size_target": None,  # 5/10/15/20
}


# --- Patch format ---
#
# IMPORTANT: The OpenAI Responses API is strict about JSON schemas. If we model
# `profile_patch` as a large object with many properties, it tends to force the
# model to emit *all* keys every time, which can lead to very large outputs and
# truncated / invalid JSON.
#
# Instead, we represent updates as a small list of "set" operations.
# Each op targets a single field path (dot-separated) and the value to set.
PATCH_OP_SCHEMA: dict = {
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
}


PROFILE_PATCH_SCHEMA: dict = {
    "type": "array",
    "items": PATCH_OP_SCHEMA,
    "maxItems": 12,
}


# JSON schema used to force the model to return structured next-turn objects.
NEXT_TURN_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {
            "type": "string",
            "enum": ["ASK", "CLARIFY", "FINISH", "END_NOT_US"],
        },
        "question": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "id": {"type": "string"},
                "text": {"type": "string", "minLength": 1},
                "answer_type": {
                    "type": "string",
                    "enum": ["text", "number", "choice", "multi_choice"],
                },
                "options": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["id", "text", "answer_type", "options"],
        },
        "profile_patch": PROFILE_PATCH_SCHEMA,
        "note_to_user": {"type": "string"},
    },
    "required": ["action", "question", "profile_patch", "note_to_user"],
}

# Priority fields the intake agent should try to fill early.
PRIORITY_SLOTS: list[str] = [
    "us_only",
    "residency_status",
    "state_of_residence",
    "applicant_type",
    "intended_major_primary",
    "budget_range_all_in",
    # At least one of these two should get filled early:
    "regions_open_to",
    "distance_preference",
]


# Full-depth intake order as field paths.
#
# The model should use these paths as question ids (and patch op paths).
DEEP_PATHS_ORDER: list[str] = [
    # Gatekeeping + type
    "us_only",
    "residency_status",
    "state_of_residence",
    "applicant_type",
    "entry_term",
    "hs_grad_year",
    "college_gpa",

    # Major & goals
    "intended_major_primary",
    "intended_major_alternates",
    "major_certainty",
    "career_goal",
    "grad_school_plan",

    # Budget & aid
    "budget_range_all_in",
    "loan_tolerance",
    "in_state_importance",
    "fafsa_intent",
    "css_profile_willing",

    # Preferences
    "regions_open_to",
    "distance_preference",
    "setting_preference",
    "campus_size_pref",
    "vibe_pref",

    # Academics snapshot
    "gpa_unweighted",
    "gpa_weighted",
    "class_rank",
    "highest_math",
    "highest_science",
    "rigor_tags",

    # Testing
    "test_strategy",
    "sat.status",
    "sat.best_total",
    "sat.ebrw",
    "sat.math",
    "act.status",
    "act.best_composite",

    # Constraints & activities
    "hard_dealbreakers",
    "soft_preferences",
    "top_activities",

    # Output preference
    "want_reach_match_safety",
    "list_size_target",
]
