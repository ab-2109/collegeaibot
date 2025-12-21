from typing import List
from pydantic import BaseModel, Field

class CVImprovement(BaseModel):
    section: str = Field(..., description="e.g., 'Extracurriculars', 'Essays', 'Awards'")
    current_weakness: str = Field(..., description="What is currently lacking or generic")
    suggestion: str = Field(..., description="Specific action to take (e.g., 'Quantify impact', 'Highlight leadership')")
    target_college_context: str = Field(..., description="Why this change matters for the specific target schools")

class CVReviewOutput(BaseModel):
    strategic_summary: str = Field(..., description="High-level strategy for the application")
    improvements: List[CVImprovement]