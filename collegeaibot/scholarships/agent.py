from __future__ import annotations

import copy
import os
import re
from datetime import date
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

from ..intake.agent import _get_by_path, apply_patch_ops
from ..intake.client import DEFAULT_MODEL, get_openai_client
from .schemas import NextTurn


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _is_set(v: Any) -> bool:
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
class ScholarshipsConfig:
    max_recommendations: int = 8


SYSTEM_INSTRUCTIONS = """
You are a scholarships recommender.

Constraints:
- There is NO internal scholarships database/catalog available.
- You MUST return real scholarships that actually exist.
- Include a direct link to the scholarship's official page (provider/foundation/university page). Do NOT use aggregator-only pages.
- If you are not confident a scholarship exists and you cannot provide an official link, do not include it.
- Deadlines must be specific and returned as an ISO date string YYYY-MM-DD when available.
- Prefer scholarships tied to the colleges already recommended (institutional scholarships / scholarship portals / priority deadlines),
  and then add a small number of national external scholarships.
- Ask at most ONE question per turn, only if it would materially improve the recommendations.
- If you ask a question, set question.id to a dot-path where the answer should be stored in the profile.
    Prefer storing scholarship-only fields under the 'scholarships.' namespace.

Output MUST be valid JSON that matches the provided schema.
""".strip()


_VERIFY_TIMEOUT_S = float(os.getenv("COLLEGEAIBOT_SCHOLARSHIPS_VERIFY_TIMEOUT_S", "10"))
_FETCH_TEXT_TIMEOUT_S = float(os.getenv("COLLEGEAIBOT_SCHOLARSHIPS_FETCH_TIMEOUT_S", "12"))


_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def _parse_date_str(s: str) -> Optional[str]:
    """Parse common date strings into ISO YYYY-MM-DD when possible."""

    s = (s or "").strip()
    if not s:
        return None

    # Already ISO
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s

    m = re.search(
        r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?\s*,\s*(\d{4})",
        s,
        flags=re.IGNORECASE,
    )
    if m:
        month = _MONTHS.get(m.group(1).lower())
        day = int(m.group(2))
        year = int(m.group(3))
        try:
            return date(year, month, day).isoformat()
        except Exception:
            return None

    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", s)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        year = int(m.group(3))
        if year < 100:
            year += 2000
        try:
            return date(year, month, day).isoformat()
        except Exception:
            return None

    return None


def _fetch_page_text(url: str) -> str:
    try:
        with httpx.Client(timeout=httpx.Timeout(_FETCH_TEXT_TIMEOUT_S), follow_redirects=True) as c:
            r = c.get(url, headers={"User-Agent": "collegeaibot/1.0"})
            if r.status_code >= 400:
                return ""
            html = r.text
    except Exception:
        return ""

    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = " ".join(soup.get_text(" ").split())
        return text
    except Exception:
        return ""


def _extract_deadline_iso(url: str) -> Optional[str]:
    text = _fetch_page_text(url)
    if not text:
        return None

    low = text.lower()
    # Prioritize context near the word 'deadline'
    idx = low.find("deadline")
    windows: List[str] = []
    if idx != -1:
        start = max(0, idx - 250)
        end = min(len(text), idx + 350)
        windows.append(text[start:end])
    windows.append(text[:1500])

    patterns = [
        r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b\s+\d{1,2}(?:st|nd|rd|th)?\s*,\s*\d{4}",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
    ]

    for w in windows:
        for pat in patterns:
            m = re.search(pat, w, flags=re.IGNORECASE)
            if m:
                iso = _parse_date_str(m.group(0))
                if iso:
                    return iso

    return None


def _get_first_college_names(advisor_data: Optional[Dict[str, Any]], max_n: int = 10) -> List[str]:
    if not isinstance(advisor_data, dict):
        return []
    recs = advisor_data.get("recommendations")
    if not isinstance(recs, list):
        return []
    names: List[str] = []
    for r in recs[:max_n]:
        if isinstance(r, dict) and r.get("college_name"):
            names.append(str(r.get("college_name")))
    return names


def _get_college_scholarship_urls(advisor_data: Optional[Dict[str, Any]], max_n: int = 10) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not isinstance(advisor_data, dict):
        return out
    recs = advisor_data.get("recommendations")
    if not isinstance(recs, list):
        return out
    for r in recs[:max_n]:
        if not isinstance(r, dict):
            continue
        name = r.get("college_name")
        if not name:
            continue
        url = r.get("scholarship_website") or r.get("admission_website")
        if isinstance(url, str) and url.startswith("http"):
            out[str(name)] = url
    return out


GATING_QUESTIONS: List[Dict[str, Any]] = [
    {
        "id": "scholarships.student_level",
        "text": "What is your current student level for scholarship eligibility?",
        "answer_type": "choice",
        "options": ["High school senior", "High school junior", "College freshman", "Transfer applicant", "Other", "Skip"],
    },
    {
        "id": "scholarships.citizenship",
        "text": "What is your citizenship/residency status (for scholarship eligibility)?",
        "answer_type": "choice",
        "options": ["U.S. citizen", "Permanent resident", "International", "Other", "Prefer not to say", "Skip"],
    },
    {
        "id": "scholarships.state_of_residence",
        "text": "Which U.S. state do you live in (or are you applying from)?",
        "answer_type": "text",
        "options": ["Skip"],
    },
    {
        "id": "scholarships.household_income_range",
        "text": "Rough household income range (helps need-based aid + some programs)?",
        "answer_type": "choice",
        "options": ["<$40k", "$40k–$80k", "$80k–$140k", "$140k+", "Not sure", "Prefer not to say", "Skip"],
    },
    {
        "id": "scholarships.identity_scholarships_opt_in",
        "text": "Do you want me to include identity-based scholarships (gender/ethnicity/etc.)?",
        "answer_type": "choice",
        "options": ["Yes", "No", "Prefer not to say"],
    },
    {
        "id": "scholarships.ethnicity",
        "text": "Which eligibility group(s) apply (for identity-based scholarships)?",
        "answer_type": "multi_choice",
        "options": [
            "Asian",
            "Black/African American",
            "Hispanic/Latino",
            "Middle Eastern/North African",
            "Native/Indigenous",
            "Pacific Islander",
            "White",
            "Multiracial",
            "Prefer not to say",
            "Skip",
        ],
        "depends_on": {"path": "scholarships.identity_scholarships_opt_in", "equals": "Yes"},
    },
]


def _next_gating_question(profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for q in GATING_QUESTIONS:
        dep = q.get("depends_on")
        if dep:
            dep_val = _get_by_path(profile, dep.get("path"))
            if dep_val != dep.get("equals"):
                continue
        if not _is_set(_get_by_path(profile, q["id"])):
            return {k: v for k, v in q.items() if k != "depends_on"}
    return None


def _verify_link(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    if not (url.startswith("http://") or url.startswith("https://")):
        return False

    try:
        with httpx.Client(timeout=httpx.Timeout(_VERIFY_TIMEOUT_S), follow_redirects=True) as c:
            r = c.get(url, headers={"User-Agent": "collegeaibot/1.0"})
            if r.status_code >= 400:
                return False
            return True
    except Exception:
        return False


def _patch_for_answer(question_id: str, answer: str) -> List[Dict[str, Any]]:
    a = (answer or "").strip()
    if not question_id or not a:
        return []

    # Best-effort numeric parsing for obvious numeric answers.
    try:
        if _norm(a).replace(".", "", 1).isdigit():
            return [{"path": question_id, "value": float(a)}]
    except Exception:
        pass

    return [{"path": question_id, "value": a}]


class ScholarshipsAgent:
    def __init__(self, config: Optional[ScholarshipsConfig] = None, model: str = DEFAULT_MODEL) -> None:
        self.config = config or ScholarshipsConfig()
        self.client = get_openai_client()
        self.model = model

    def next_turn(
        self,
        profile: Dict[str, Any],
        last_user_answer: Optional[str],
        last_question_id: Optional[str] = None,
        advisor_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        updated_profile = copy.deepcopy(profile)

        # Gatekeeping: this node is designed for US-oriented scholarship search.
        if _get_by_path(updated_profile, "us_only") is False:
            turn = NextTurn(
                action="END_NOT_US",
                question=None,
                profile_patch=[],
                note_to_user="This scholarships flow currently targets US-based scholarships.",
                recommendations=None,
            )
            return turn.model_dump(mode="json"), updated_profile

        # Apply the last answer to the profile.
        user_ops: List[Dict[str, Any]] = []
        if last_question_id and last_user_answer is not None:
            user_ops = _patch_for_answer(last_question_id, last_user_answer)
            if user_ops:
                apply_patch_ops(updated_profile, user_ops)

        # If no API key is configured, provide a helpful clarify response.
        if not os.getenv("OPENAI_API_KEY"):
            turn = NextTurn(
                action="CLARIFY",
                question=None,
                profile_patch=user_ops,
                note_to_user="Set OPENAI_API_KEY (or a .env file) to use the scholarships recommender.",
                recommendations=None,
            )
            return turn.model_dump(mode="json"), updated_profile

        # Ask/recommend based on the profile (no scholarships database).
        # Deterministic gating: ask key eligibility questions first.
        gq = _next_gating_question(updated_profile)
        if gq is not None:
            turn = NextTurn(
                action="ASK",
                question=gq,
                profile_patch=user_ops,
                note_to_user="Quick eligibility question so I can target the right college-specific scholarships.",
                recommendations=None,
            )
            return turn.model_dump(mode="json"), updated_profile

        advisor_summary = None
        advisor_recs = None
        if isinstance(advisor_data, dict):
            advisor_summary = advisor_data.get("summary")
            advisor_recs = advisor_data.get("recommendations")

        college_names = _get_first_college_names(advisor_data)
        college_urls = _get_college_scholarship_urls(advisor_data)

        messages = [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {
                "role": "user",
                "content": (
                    "STUDENT PROFILE (JSON):\n"
                    f"{updated_profile}\n\n"
                    "ADVISOR OUTPUT (JSON, may be null):\n"
                    f"{{'summary': {advisor_summary!r}, 'recommendations': {advisor_recs!r}}}\n\n"
                    "COLLEGES TO PRIORITIZE (from advisor):\n"
                    f"{college_names!r}\n\n"
                    "KNOWN OFFICIAL PAGES (from advisor; use these as starting points):\n"
                    f"{college_urls!r}\n\n"
                    "Decide the next turn. If recommending, return scholarships with official links.\n"
                    "Rules for recommendations:\n"
                    "- Include as many college-specific institutional scholarship opportunities as possible for the advisor colleges.\n"
                    "- For colleges with no merit scholarships (e.g., need-based only), include their official financial aid deadlines.\n"
                    "- Provide ISO deadlines YYYY-MM-DD when possible (do not say 'varies by year').\n"
                    "- If a specific deadline is not on the official page, set deadline=null.\n"
                    "- Keep total recommendations <= "
                    f"{self.config.max_recommendations}."
                ),
            },
        ]

        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=NextTurn,
        )

        parsed: NextTurn = completion.choices[0].message.parsed
        turn_dict: Dict[str, Any] = parsed.model_dump(mode="json")

        # Apply any model-provided patch ops (e.g., derived normalization).
        model_ops = [op.model_dump(mode="json") for op in (parsed.profile_patch or [])]
        if model_ops:
            apply_patch_ops(updated_profile, model_ops)

        # Ensure the caller persists both the user's last answer and any model-derived updates.
        turn_dict["profile_patch"] = user_ops + model_ops

        # Defensive: cap + verify scholarship links.
        recs = turn_dict.get("recommendations")
        if isinstance(recs, list):
            recs = recs[: self.config.max_recommendations]
            verified: List[Dict[str, Any]] = []
            for r in recs:
                if not isinstance(r, dict):
                    continue
                link = (r or {}).get("link")
                if not _verify_link(link):
                    continue
                # Deadline normalization/extraction
                dl = r.get("deadline")
                iso = _parse_date_str(str(dl)) if dl else None
                if iso is None:
                    iso = _extract_deadline_iso(str(link))
                r["deadline"] = iso
                verified.append(r)
            turn_dict["recommendations"] = verified

            if turn_dict.get("action") == "RECOMMEND" and not verified:
                turn_dict["action"] = "CLARIFY"
                turn_dict["note_to_user"] = (
                    "I couldn't verify the scholarship links I generated. "
                    "Please share your constraints (citizenship, ethnicity if relevant, state, household income range, and student level), "
                    "or provide a shortlist of scholarship providers/universities to target."
                )
                turn_dict["question"] = None

        return turn_dict, updated_profile
