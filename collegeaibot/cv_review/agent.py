import json
from typing import Dict, Any, List

from ..intake.client import get_openai_client, DEFAULT_MODEL
from .prompts import CV_REVIEW_SYSTEM_INSTRUCTIONS
from .schemas import CVReviewOutput

class CVReviewAgent:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.client = get_openai_client()
        self.model = model

    def analyze_cv(self, user_profile: Dict[str, Any], advisor_recommendations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyzes profile against specific high-priority college recommendations.
        """
        
        # 1. Filter for Reach/Target only
        target_schools = [
            rec for rec in advisor_recommendations 
            if rec.get("category") in ["Extreme Reach", "Target Match"]
        ]

        if not target_schools:
            return {
                "strategic_summary": "No Reach or Target schools found to analyze.",
                "improvements": []
            }

        # 2. Construct Prompt
        messages = [
            {"role": "system", "content": CV_REVIEW_SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": f"""
            STUDENT PROFILE:
            {json.dumps(user_profile, indent=2)}

            TARGET COLLEGES (Reach/Target only):
            {json.dumps(target_schools, indent=2)}

            Provide specific CV improvements to maximize acceptance chances.
            """}
        ]

        # 3. Call LLM
        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=CVReviewOutput,
        )

        return completion.choices[0].message.parsed.model_dump()