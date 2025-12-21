import sys
import json
from pathlib import Path
from .agent import CVReviewAgent

def run_cv_demo(client_id: str):
    # 1. Setup Paths
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent.parent
    
    profile_path = project_root / "data" / "intake_profiles.json"
    advisor_path = project_root / "data" / "advisor_results.json"

    # 2. Load Profile
    if not profile_path.exists():
        print("❌ No profiles found. Run intake first.")
        return

    with open(profile_path, "r") as f:
        all_profiles = json.load(f)
    
    profile = all_profiles.get(client_id)
    if not profile:
        print(f"❌ Profile '{client_id}' not found.")
        return

    # 3. Load Real Advisor Recommendations
    print(f"--- Retrieving Target Schools for {client_id} ---")
    
    if not advisor_path.exists():
        print("❌ No advisor results found. You must run the ADVISOR demo first!")
        return

    with open(advisor_path, "r") as f:
        all_advisor_results = json.load(f)
    
    advisor_data = all_advisor_results.get(client_id)
    if not advisor_data:
        print(f"❌ No recommendations found for '{client_id}'. Run advisor demo first.")
        return

    # Extract the list of recommendations
    recommendations = advisor_data.get("recommendations", [])
    
    if not recommendations:
        print("⚠️ No recommendations list found in advisor output.")

    # 4. Run CV Agent
    print("--- Analyzing CV Strategy ---")
    agent = CVReviewAgent()
    result = agent.analyze_cv(profile, recommendations)

    # 5. Print Results
    print("\n=== STRATEGIC SUMMARY ===")
    print(result["strategic_summary"])
    print("\n=== CV IMPROVEMENTS ===")
    for i, imp in enumerate(result["improvements"], 1):
        print(f"{i}. Section: {imp['section']}")
        print(f"   Weakness: {imp['current_weakness']}")
        print(f"   👉 FIX: {imp['suggestion']}")
        print(f"   Why: {imp['target_college_context']}")
        print("-" * 40)

if __name__ == "__main__":
    user_id = sys.argv[1] if len(sys.argv) > 1 else "demo-user"
    run_cv_demo(user_id)