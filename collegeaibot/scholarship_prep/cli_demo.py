"""CLI demo for the scholarship prep agent.

Usage:
    python -m collegeaibot.scholarship_prep.cli_demo
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from ..intake.storage import JsonFileProfileStore
from ..scholarships.storage import JsonFileScholarshipStore
from .agent import ScholarshipPrepAgent


def run_cli(client_id: Optional[str] = None) -> None:
    client_id = client_id or os.getenv("CLIENT_ID", "demo-user")

    print(f"Starting scholarship prep advisor for client_id={client_id}\n")

    # Load intake profile
    intake_store = JsonFileProfileStore()
    scholarships_store = JsonFileScholarshipStore()

    intake_profile = intake_store.get_profile(client_id)
    scholarships_profile = scholarships_store.get_profile(client_id)

    # Merge profiles
    merged = dict(intake_profile)
    if isinstance(scholarships_profile, dict):
        merged.update(scholarships_profile)

    # Load scholarship recommendations if available
    scholarship_recommendations = None
    try:
        current_dir = Path(__file__).resolve().parent
        project_root = current_dir.parent.parent
        scholarships_results_path = project_root / "data" / "scholarship_recommendations.json"
        if scholarships_results_path.exists():
            with scholarships_results_path.open("r", encoding="utf-8") as f:
                all_results = json.load(f)
            scholarship_recommendations = all_results.get(client_id, {}).get("recommendations", [])
            if scholarship_recommendations:
                print(f"Loaded {len(scholarship_recommendations)} scholarship recommendations.\n")
    except Exception as e:
        print(f"Note: Could not load scholarship recommendations: {e}\n")

    agent = ScholarshipPrepAgent()

    last_answer: Optional[str] = None
    last_question_id: Optional[str] = None

    while True:
        response, updated_profile = agent.next_turn(
            profile=merged,
            last_user_answer=last_answer,
            last_question_id=last_question_id,
            scholarship_recommendations=scholarship_recommendations,
        )
        merged = updated_profile

        action = response.get("action")

        # Save profile updates
        if response.get("profile_patch"):
            intake_store.update_profile(client_id, response["profile_patch"])

        if action == "ASK":
            q = response.get("question", {})
            print(f"Question: {q.get('text', '')}")
            if q.get("options"):
                print("Options:")
                for i, opt in enumerate(q["options"], 1):
                    print(f"  {i}. {opt}")
            user_input = input("Your answer: ").strip()
            last_answer = user_input
            last_question_id = q.get("id")

        elif action == "CLARIFY":
            note = response.get("note_to_user", "")
            print(f"\n[Note] {note}")
            user_input = input("Your response (or 'quit'): ").strip()
            if user_input.lower() in ("quit", "exit", "q"):
                break
            last_answer = user_input
            last_question_id = None

        elif action == "SUGGEST":
            note = response.get("note_to_user", "")
            if note:
                print(f"\n{note}\n")

            summary = response.get("summary")
            if summary:
                print(f"SUMMARY:\n{summary}\n")

            suggestions = response.get("suggestions", [])
            if suggestions:
                print("=" * 70)
                print("PERSONALIZED SUGGESTIONS TO STRENGTHEN YOUR SCHOLARSHIP APPLICATIONS")
                print("=" * 70)

                for i, sug in enumerate(suggestions, 1):
                    print(f"\n{i}. {sug.get('title', 'Untitled')}")
                    print(f"   Category: {sug.get('category', 'other').replace('_', ' ').title()}")
                    print(f"   Priority: {sug.get('priority', 'medium').upper()}")
                    print(f"   Difficulty: {sug.get('difficulty', 'moderate').title()}")

                    if sug.get("description"):
                        print(f"   Description: {sug['description']}")

                    if sug.get("target_scholarships"):
                        print(f"   Helps with: {', '.join(sug['target_scholarships'][:3])}")

                    if sug.get("link"):
                        print(f"   Link: {sug['link']}")

                    if sug.get("deadline"):
                        print(f"   Deadline: {sug['deadline']}")

                    if sug.get("estimated_time"):
                        print(f"   Time Commitment: {sug['estimated_time']}")

                    if sug.get("action_steps"):
                        print("   Action Steps:")
                        for step in sug["action_steps"][:4]:
                            print(f"      • {step}")

            # Save recommendations to file
            try:
                current_dir = Path(__file__).resolve().parent
                project_root = current_dir.parent.parent
                output_path = project_root / "data" / "prep_suggestions.json"
                output_path.parent.mkdir(parents=True, exist_ok=True)

                existing = {}
                if output_path.exists():
                    with output_path.open("r", encoding="utf-8") as f:
                        existing = json.load(f)

                existing[client_id] = {
                    "suggestions": suggestions,
                    "summary": summary,
                }

                with output_path.open("w", encoding="utf-8") as f:
                    json.dump(existing, f, ensure_ascii=False, indent=2)

                print(f"\n[Saved suggestions to {output_path}]")
            except Exception as e:
                print(f"\n[Could not save suggestions: {e}]")

            break

        elif action == "END":
            note = response.get("note_to_user", "Thank you!")
            print(f"\n{note}")
            break

        else:
            print(f"Unknown action: {action}")
            break


if __name__ == "__main__":
    run_cli()
