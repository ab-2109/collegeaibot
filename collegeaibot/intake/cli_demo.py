"""Minimal CLI demo for the intake agent.

This is *not* meant to be production-facing, but gives you a quick way
to exercise the agent logic end-to-end and will be useful later when
wiring into LangGraph or an API server.
"""

from __future__ import annotations

import os
from typing import Optional

from .agent import IntakeAgent, IntakeConfig, new_profile
from .storage import JsonFileProfileStore


def run_cli(client_id: Optional[str] = None) -> None:
    client_id = client_id or os.getenv("CLIENT_ID", "demo-user")

    store = JsonFileProfileStore()
    agent = IntakeAgent(config=IntakeConfig(completion_mode="deep"))

    profile = store.get_profile(client_id)
    last_answer: Optional[str] = None
    last_question_id: Optional[str] = None

    print(f"Starting intake for client_id={client_id}\n")

    while True:
        response, updated_profile = agent.next_turn(profile, last_answer, last_question_id=last_question_id)

        # Persist progress (critical)
        profile_patch = response.get("profile_patch") or []
        store.update_profile(client_id, profile_patch)

        profile = updated_profile

        action = response["action"]
        question = response.get("question")
        note = response.get("note_to_user")

        if note:
            print(f"[Note] {note}")

        if action == "END_NOT_US":
            print("\nYou indicated you are not applying to US colleges. Ending intake.")
            break

        if action == "FINISH":
            print("\nIntake finished. Final profile:")
            print(profile)
            break

        if action in {"ASK", "CLARIFY"} and question is not None:
            last_question_id = question.get("id")
            print(f"\n{question['text']}")
            if question.get("options"):
                print("Options: " + ", ".join(question["options"]))

            last_answer = input("> ").strip()
        else:
            # Fallback: no question but not finished; avoid tight loop.
            print("Model did not provide a valid question; stopping.")
            break


if __name__ == "__main__":
    run_cli()
