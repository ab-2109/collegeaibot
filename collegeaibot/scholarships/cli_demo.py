from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from ..intake.storage import JsonFileProfileStore
from .agent import ScholarshipsAgent
from .storage import JsonFileScholarshipStore


def run_cli(client_id: Optional[str] = None) -> None:
    client_id = client_id or os.getenv("CLIENT_ID", "demo-user")

    # Optional advisor output (college list) to tailor institutional scholarship leads.
    advisor_data = None
    try:
        current_dir = Path(__file__).resolve().parent
        project_root = current_dir.parent.parent
        advisor_path = project_root / "data" / "advisor_results.json"
        if advisor_path.exists():
            with advisor_path.open("r", encoding="utf-8") as f:
                all_advisor_results = json.load(f)
            advisor_data = all_advisor_results.get(client_id)
    except Exception:
        advisor_data = None

    intake_store = JsonFileProfileStore()
    scholarships_store = JsonFileScholarshipStore()

    intake_profile = intake_store.get_profile(client_id)
    scholarships_profile = scholarships_store.get_profile(client_id)

    # Merge scholarship-specific fields into the intake profile for matching.
    # We keep them under the "scholarships" namespace.
    merged = dict(intake_profile)
    if isinstance(scholarships_profile, dict):
        merged.update(scholarships_profile)

    agent = ScholarshipsAgent()

    last_answer: Optional[str] = None
    last_question_id: Optional[str] = None

    print(f"Starting scholarships recommender for client_id={client_id}\n")

    while True:
        response, updated = agent.next_turn(
            merged,
            last_answer,
            last_question_id=last_question_id,
            advisor_data=advisor_data,
        )

        # Persist only the patch ops into the scholarships profile store.
        patch_ops = response.get("profile_patch") or []
        if patch_ops:
            scholarships_store.update_profile(client_id, patch_ops)

        merged = updated

        note = response.get("note_to_user")
        if note:
            print(f"[Note] {note}")

        if response["action"] == "END_NOT_US":
            print("\nNot eligible for US-only scholarships node.")
            break

        if response["action"] == "RECOMMEND":
            recs = response.get("recommendations") or []
            print("\nScholarships (verified links):")
            for i, r in enumerate(recs, 1):
                print(f"\n{i}. {r.get('name')}")
                if r.get("college"):
                    print(f"   College: {r.get('college')}")
                if r.get("kind"):
                    print(f"   Kind: {r.get('kind')}")
                if r.get("provider"):
                    print(f"   Provider: {r.get('provider')}")
                if r.get("award"):
                    print(f"   Award: {r.get('award')}")
                if r.get("deadline"):
                    print(f"   Deadline: {r.get('deadline')}")
                if r.get("link"):
                    print(f"   Link: {r.get('link')}")
                if r.get("why_suitable"):
                    print(f"   Why: {r.get('why_suitable')}")
                elig = r.get("key_eligibility") or []
                if elig:
                    print("   Eligibility: " + "; ".join(elig[:4]))
                steps = r.get("how_to_apply") or []
                if steps:
                    print("   Apply: " + "; ".join(steps[:4]))
            break

        q = response.get("question")
        if not q:
            print("No question provided; stopping.")
            break

        last_question_id = q["id"]
        print(f"\n{q['text']}")
        if q.get("options"):
            print("Options: " + ", ".join(q["options"]))
        last_answer = input("> ").strip()


if __name__ == "__main__":
    run_cli()
