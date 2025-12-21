import json
from typing import Dict, Any

from ..intake.client import get_openai_client, DEFAULT_MODEL
from .prompts import ADVISOR_SYSTEM_INSTRUCTIONS
from .schemas import AdvisorOutput
from .tools import search_colleges

class AdvisorAgent:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.client = get_openai_client()
        self.model = model

    def generate_recommendations(self, user_profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        1. Search for colleges based on profile.
        2. Send profile + search results to LLM.
        3. Return structured recommendations.
        """
        
        # 1. Tool Step: Get raw data
        potential_matches = search_colleges(user_profile)

        # 2. Construct Prompt
        messages = [
            {"role": "system", "content": ADVISOR_SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": f"""
            Here is the Student Profile:
            {json.dumps(user_profile, indent=2)}

            Here is a list of potential colleges found in our database:
            {json.dumps(potential_matches, indent=2)}

            Based on this, generate a final recommendation list.
            """}
        ]

        # 3. Call LLM with Structured Output (Pydantic)
        # Note: We use the 'beta.parse' helper which is available in newer OpenAI SDKs
        # to automatically validate against our Pydantic model.
        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=AdvisorOutput,
        )

        # 4. Return the parsed object as a dict
        return completion.choices[0].message.parsed.model_dump()