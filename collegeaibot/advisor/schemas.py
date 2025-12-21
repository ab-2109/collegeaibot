from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field

class MatchCategory(str, Enum):
    EXTREME_REACH = "Extreme Reach"
    TARGET_MATCH = "Target Match"
    SAFETY = "Safety"

class CollegeRecommendation(BaseModel):
    college_name: str
    location: str
    category: MatchCategory = Field(..., description="Categorization of the school based on student stats")
    match_score: int = Field(..., description="Score from 0-100 on how well this fits the student")
    reasoning: str = Field(..., description="Why this college fits the student's profile")
    tuition_estimate: Optional[str] = None
    application_deadline: Optional[str] = Field(None, description="Upcoming relevant deadline")
    admission_website: Optional[str] = Field(None, description="Official URL for admissions page")
    scholarship_info: Optional[str] = Field(None, description="Relevant scholarship opportunities")
    scholarship_website: Optional[str] = Field(None, description="URL for financial aid or scholarship page")

class AdvisorOutput(BaseModel):
    summary: str = Field(..., description="A friendly summary of the analysis")
    recommendations: List[CollegeRecommendation]