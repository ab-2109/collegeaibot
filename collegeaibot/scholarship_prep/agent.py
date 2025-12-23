"""Scholarship preparation agent - suggests programs, internships, and improvements
to increase chances for recommended scholarships.

This agent:
1. Takes the student's intake profile and scholarship recommendations
2. Asks additional questions about their current activities, skills, and availability
3. Provides personalized suggestions for programs, internships, competitions, etc.
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..intake.agent import _get_by_path, apply_patch_ops
from ..intake.client import DEFAULT_MODEL, get_openai_client
from .schemas import NextTurn, Question, Action


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _is_set(v: Any) -> bool:
    """Check if a profile value is meaningfully set."""
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, list):
        return len(v) > 0
    if isinstance(v, dict):
        return any(_is_set(x) for x in v.values())
    return True


@dataclass(frozen=True)
class ScholarshipPrepConfig:
    """Configuration for the scholarship prep agent."""

    max_suggestions: int = 15
    max_questions: int = 8


# Questions to ask about student's current profile for prep recommendations
PREP_QUESTIONS: List[Dict[str, Any]] = [
    {
        "id": "prep.current_extracurriculars",
        "text": "What extracurricular activities are you currently involved in? (clubs, sports, arts, etc.)",
        "answer_type": "text",
        "options": [],
    },
    {
        "id": "prep.leadership_roles",
        "text": "Do you hold any leadership positions? If so, describe them.",
        "answer_type": "text",
        "options": [],
    },
    {
        "id": "prep.work_experience",
        "text": "Do you have any work experience, internships, or research experience?",
        "answer_type": "text",
        "options": [],
    },
    {
        "id": "prep.volunteer_service",
        "text": "What volunteer or community service activities have you participated in?",
        "answer_type": "text",
        "options": [],
    },
    {
        "id": "prep.technical_skills",
        "text": "What technical skills do you have? (programming languages, software, tools, etc.)",
        "answer_type": "text",
        "options": [],
    },
    {
        "id": "prep.competitions_awards",
        "text": "Have you participated in any competitions or received any awards/honors?",
        "answer_type": "text",
        "options": [],
    },
    {
        "id": "prep.available_hours_weekly",
        "text": "How many hours per week can you dedicate to scholarship prep activities?",
        "answer_type": "choice",
        "options": ["Less than 5 hours", "5-10 hours", "10-15 hours", "15-20 hours", "20+ hours"],
    },
    {
        "id": "prep.timeline",
        "text": "When do you plan to start college?",
        "answer_type": "choice",
        "options": ["Fall 2025", "Spring 2026", "Fall 2026", "Spring 2027", "Fall 2027", "Later"],
    },
]


def _next_prep_question(profile: Dict[str, Any]) -> Optional[Question]:
    """Return the next unanswered prep question, or None if all are answered."""
    for q in PREP_QUESTIONS:
        val = _get_by_path(profile, q["id"])
        if not _is_set(val):
            return Question(
                id=q["id"],
                text=q["text"],
                answer_type=q["answer_type"],
                options=q.get("options", []),
            )
    return None


def _patch_for_answer(question_id: str, answer: str) -> List[Dict[str, Any]]:
    """Create patch operations for storing an answer."""
    a = (answer or "").strip()
    if not question_id or not a:
        return []

    # Best-effort numeric parsing for obvious numeric answers
    try:
        if _norm(a).replace(".", "", 1).isdigit():
            return [{"path": question_id, "value": float(a)}]
    except Exception:
        pass

    return [{"path": question_id, "value": a}]


def _format_scholarships_for_prompt(scholarships: List[Dict[str, Any]]) -> str:
    """Format scholarship recommendations for the LLM prompt."""
    if not scholarships:
        return "No scholarships have been recommended yet."

    lines = ["Recommended Scholarships:"]
    for i, sch in enumerate(scholarships, 1):
        name = sch.get("name", "Unknown")
        provider = sch.get("provider", "Unknown")
        kind = sch.get("kind", "external")
        award = sch.get("award", "Varies")
        deadline = sch.get("deadline", "Check website")
        eligibility = sch.get("key_eligibility", [])

        lines.append(f"\n{i}. {name}")
        lines.append(f"   Provider: {provider}")
        lines.append(f"   Type: {kind}")
        lines.append(f"   Award: {award}")
        lines.append(f"   Deadline: {deadline}")
        if eligibility:
            lines.append(f"   Key Requirements: {'; '.join(eligibility[:3])}")

    return "\n".join(lines)


def _format_profile_for_prompt(profile: Dict[str, Any]) -> str:
    """Format the student profile for the LLM prompt."""
    sections = []

    # Academic info
    academic = []
    if profile.get("gpa_unweighted"):
        academic.append(f"GPA (Unweighted): {profile['gpa_unweighted']}")
    if profile.get("gpa_weighted"):
        academic.append(f"GPA (Weighted): {profile['gpa_weighted']}")
    if profile.get("sat", {}).get("best_total"):
        academic.append(f"SAT: {profile['sat']['best_total']}")
    if profile.get("act", {}).get("best_composite"):
        academic.append(f"ACT: {profile['act']['best_composite']}")
    if profile.get("intended_major_primary"):
        academic.append(f"Intended Major: {profile['intended_major_primary']}")
    if profile.get("class_rank"):
        academic.append(f"Class Rank: {profile['class_rank']}")
    if academic:
        sections.append("ACADEMIC PROFILE:\n" + "\n".join(f"  - {x}" for x in academic))

    # Demographics
    demo = []
    if profile.get("residency_status"):
        demo.append(f"Residency: {profile['residency_status']}")
    if profile.get("scholarships", {}).get("state_of_residence"):
        demo.append(f"State: {profile['scholarships']['state_of_residence']}")
    if profile.get("scholarships", {}).get("ethnicity"):
        demo.append(f"Ethnicity: {profile['scholarships']['ethnicity']}")
    if profile.get("scholarships", {}).get("household_income_range"):
        demo.append(f"Household Income: {profile['scholarships']['household_income_range']}")
    if demo:
        sections.append("DEMOGRAPHICS:\n" + "\n".join(f"  - {x}" for x in demo))

    # Current activities (from prep questions)
    prep = profile.get("prep", {})
    if prep:
        activities = []
        if prep.get("current_extracurriculars"):
            activities.append(f"Extracurriculars: {prep['current_extracurriculars']}")
        if prep.get("leadership_roles"):
            activities.append(f"Leadership: {prep['leadership_roles']}")
        if prep.get("work_experience"):
            activities.append(f"Work/Internship Experience: {prep['work_experience']}")
        if prep.get("volunteer_service"):
            activities.append(f"Volunteer/Service: {prep['volunteer_service']}")
        if prep.get("technical_skills"):
            activities.append(f"Technical Skills: {prep['technical_skills']}")
        if prep.get("competitions_awards"):
            activities.append(f"Competitions/Awards: {prep['competitions_awards']}")
        if prep.get("available_hours_weekly"):
            activities.append(f"Available Hours/Week: {prep['available_hours_weekly']}")
        if prep.get("timeline"):
            activities.append(f"College Start: {prep['timeline']}")
        if activities:
            sections.append("CURRENT ACTIVITIES & AVAILABILITY:\n" + "\n".join(f"  - {x}" for x in activities))

    return "\n\n".join(sections) if sections else "Limited profile information available."


SYSTEM_INSTRUCTIONS = """
You are an expert college and scholarship preparation advisor. Your goal is to suggest specific, actionable programs, internships, competitions, and improvements that will strengthen the student's scholarship applications.

Given:
1. The student's current profile (academics, demographics, activities)
2. Their recommended scholarships

Your task:
- Analyze what each scholarship is looking for
- Identify gaps between the student's current profile and scholarship requirements
- Suggest SPECIFIC, REAL programs and opportunities (with actual names and links where possible)
- Prioritize suggestions by impact and feasibility given their timeline

Categories of suggestions to include:
1. INTERNSHIPS: Summer programs, pre-college internships (Google CSSI, Microsoft Explore, NASA internships, MOSTEC, etc.)
2. PROGRAMS: Academic enrichment programs (RSI, COSMOS, SSP, MIT PRIMES, etc.)
3. COMPETITIONS: Science fairs, hackathons, olympiads, essay contests
4. VOLUNTEER/SERVICE: Community service opportunities aligned with their interests
5. COURSES/CERTIFICATIONS: Online courses, certifications that build relevant skills
6. LEADERSHIP: Ways to develop leadership experience
7. RESEARCH: Research opportunities at local universities
8. APPLICATION TIPS: Specific essay strategies and application advice for their target scholarships
9. SKILL BUILDING: Technical or soft skills to develop
10. NETWORKING: Professional connections to make

For each suggestion:
- Be SPECIFIC with program names, not generic advice
- Include official links when possible
- Note which scholarships it helps with
- Provide concrete action steps
- Consider their available time and timeline

Output MUST be valid JSON matching the provided schema with action=SUGGEST.
""".strip()


class ScholarshipPrepAgent:
    """Agent that suggests programs and improvements for scholarship preparation."""

    def __init__(
        self,
        config: Optional[ScholarshipPrepConfig] = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self.config = config or ScholarshipPrepConfig()
        self.client = get_openai_client()
        self.model = model

    def next_turn(
        self,
        profile: Dict[str, Any],
        last_user_answer: Optional[str],
        last_question_id: Optional[str] = None,
        scholarship_recommendations: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Process one turn of the scholarship prep conversation.

        Args:
            profile: The student's profile (merged intake + scholarships + prep data)
            last_user_answer: The user's answer to the previous question (if any)
            last_question_id: The ID of the question that was answered
            scholarship_recommendations: List of scholarship recommendations from the scholarships agent

        Returns:
            Tuple of (response dict, updated profile dict)
        """
        updated_profile = copy.deepcopy(profile)

        # Apply the last answer to the profile
        user_ops: List[Dict[str, Any]] = []
        if last_question_id and last_user_answer is not None:
            user_ops = _patch_for_answer(last_question_id, last_user_answer)
            if user_ops:
                apply_patch_ops(updated_profile, user_ops)

        # Check if we need to ask more questions
        next_q = _next_prep_question(updated_profile)
        if next_q is not None:
            turn = NextTurn(
                action=Action.ASK,
                question=next_q,
                profile_patch=user_ops,
                note_to_user="Let me learn more about your current activities to give you personalized suggestions.",
                suggestions=None,
            )
            return turn.model_dump(mode="json"), updated_profile

        # All questions answered - generate suggestions
        if not os.getenv("OPENAI_API_KEY"):
            turn = NextTurn(
                action=Action.CLARIFY,
                question=None,
                profile_patch=user_ops,
                note_to_user="Set OPENAI_API_KEY to use the scholarship prep advisor.",
                suggestions=None,
            )
            return turn.model_dump(mode="json"), updated_profile

        # Build the prompt
        profile_text = _format_profile_for_prompt(updated_profile)
        scholarships_text = _format_scholarships_for_prompt(scholarship_recommendations or [])

        user_message = f"""
Based on this student's profile and their recommended scholarships, provide specific suggestions for programs, internships, and improvements to strengthen their scholarship applications.

STUDENT PROFILE:
{profile_text}

{scholarships_text}

Provide up to {self.config.max_suggestions} prioritized suggestions that are:
1. Specific and actionable (real program names, not generic advice)
2. Appropriate for their timeline and available hours
3. Aligned with their target scholarships
4. Feasible given their current skill level

Focus especially on:
- Programs that directly address eligibility requirements for their top scholarships
- Opportunities that fill gaps in their current profile
- High-impact activities that multiple scholarships value

Return your response as JSON with action=SUGGEST.
""".strip()

        messages = [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": user_message},
        ]

        try:
            completion = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=messages,
                response_format=NextTurn,
                temperature=0.7,
            )

            parsed = completion.choices[0].message.parsed
            if parsed is None:
                turn = NextTurn(
                    action=Action.CLARIFY,
                    question=None,
                    profile_patch=user_ops,
                    note_to_user="I couldn't generate suggestions. Please try again.",
                    suggestions=None,
                )
                return turn.model_dump(mode="json"), updated_profile

            # Merge user ops into the response
            result = parsed.model_dump(mode="json")
            if user_ops:
                existing_patch = result.get("profile_patch", [])
                result["profile_patch"] = user_ops + existing_patch

            return result, updated_profile

        except Exception as e:
            turn = NextTurn(
                action=Action.CLARIFY,
                question=None,
                profile_patch=user_ops,
                note_to_user=f"Error generating suggestions: {str(e)[:100]}",
                suggestions=None,
            )
            return turn.model_dump(mode="json"), updated_profile
