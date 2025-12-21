"""
Mock tools for the advisor agent. 
In a real app, this would connect to a vector DB or a College Scorecard API.
"""
from typing import List, Dict

# A tiny hardcoded database for demonstration
MOCK_COLLEGE_DB = [
    {
        "name": "Stanford University", 
        "location": "California", 
        "min_gpa": 3.9, 
        "major_focus": ["CS", "Engineering"], 
        "cost": "High",
        "url": "https://admission.stanford.edu/"
    },
    {
        "name": "University of Texas at Austin", 
        "location": "Texas", 
        "min_gpa": 3.5, 
        "major_focus": ["Business", "Engineering", "Arts"], 
        "cost": "Medium",
        "url": "https://admissions.utexas.edu/"
    },
    {
        "name": "Ohio State University", 
        "location": "Ohio", 
        "min_gpa": 3.0, 
        "major_focus": ["General", "Business"], 
        "cost": "Medium",
        "url": "https://undergrad.osu.edu/"
    },
    {
        "name": "Community College of Denver", 
        "location": "Colorado", 
        "min_gpa": 2.0, 
        "major_focus": ["Vocational", "General"], 
        "cost": "Low",
        "url": "https://www.ccd.edu/admission"
    },
    {
        "name": "MIT", 
        "location": "Massachusetts", 
        "min_gpa": 4.0, 
        "major_focus": ["STEM"], 
        "cost": "High",
        "url": "https://mitadmissions.org/"
    },
]

def search_colleges(profile: Dict) -> List[Dict]:
    """
    Simple logic to filter mock colleges based on GPA.
    In reality, the LLM would do the heavy lifting or we'd use a Vector DB.
    """
    gpa = float(profile.get("academics", {}).get("gpa", 0.0) or 0.0)
    
    # Simple filter: return colleges where student's GPA is within 0.5 points of min_gpa
    results = []
    for college in MOCK_COLLEGE_DB:
        if gpa >= (college["min_gpa"] - 0.5):
            results.append(college)
    
    return results