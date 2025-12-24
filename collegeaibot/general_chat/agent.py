import json
from pathlib import Path
from typing import Dict, Any, Optional

from ..intake.client import get_openai_client, DEFAULT_MODEL
from .prompts import CHAT_SYSTEM_INSTRUCTIONS

class GeneralChatAgent:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.client = get_openai_client()
        self.model = model

    def load_student_context(self, client_id: str, data_dir: Path) -> str:
        """
        Loads all 5 JSON files and aggregates data for the specific client_id.
        Returns a formatted string to be injected into the prompt.
        """
        files_to_load = [
            "intake_profiles.json",
            "advisor_results.json",
            "cv_review_results.json",
            "scholarship_recommendations.json",
            "prep_suggestions.json",
            "scholarships_profiles.json"
        ]

        aggregated_data = {}

        for filename in files_to_load:
            file_path = data_dir / filename
            key_name = filename.replace(".json", "") # e.g., "intake_profiles"
            
            if file_path.exists():
                try:
                    with open(file_path, "r") as f:
                        full_data = json.load(f)
                        # Extract only this user's data
                        user_data = full_data.get(client_id)
                        if user_data:
                            aggregated_data[key_name] = user_data
                        else:
                            aggregated_data[key_name] = "No data found for this user."
                except json.JSONDecodeError:
                    aggregated_data[key_name] = "Error reading file."
            else:
                aggregated_data[key_name] = "File not generated yet."

        return json.dumps(aggregated_data, indent=2)

    def chat(self, user_query: str, context_str: str, chat_history: list = None) -> str:
        """
        Sends the user query + full student context to the LLM.
        """
        if chat_history is None:
            chat_history = []

        # 1. System Message with Context
        system_message = {
            "role": "system", 
            "content": f"{CHAT_SYSTEM_INSTRUCTIONS}\n\n=== STUDENT FILE DATA ===\n{context_str}"
        }

        # 2. Build Message Chain
        messages = [system_message] + chat_history + [{"role": "user", "content": user_query}]

        # 3. Call OpenAI
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7 # Slightly creative for chat
        )

        return completion.choices[0].message.content