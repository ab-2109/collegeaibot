import sys
import json
import os
from pathlib import Path
from .agent import AdvisorAgent

def run_advisor_demo(client_id: str):
    # 1. Robustly find the data file
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent.parent
    data_path = project_root / "data" / "intake_profiles.json"
    results_path = project_root / "data" / "advisor_results.json"  # <--- NEW PATH

    print(f"Looking for profiles in: {data_path}")

    if not data_path.exists():
        print("❌ No profiles found. Run the intake demo first!")
        return

    with open(data_path, "r") as f:
        all_profiles = json.load(f)
    
    profile = all_profiles.get(client_id)
    if not profile:
        print(f"❌ Profile for '{client_id}' not found.")
        return

    print(f"--- Generating Recommendations for {client_id} ---")
    print("Analyzing profile...")

    # 2. Run the Advisor
    agent = AdvisorAgent()
    result = agent.generate_recommendations(profile)

    # --- NEW: SAVE RESULTS TO FILE ---
    all_results = {}
    if results_path.exists():
        try:
            with open(results_path, "r") as f:
                all_results = json.load(f)
        except json.JSONDecodeError:
            pass # Handle empty file

    all_results[client_id] = result

    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2)
    
    print(f"✅ Recommendations saved to {results_path}")
    # ---------------------------------

    # 3. Print Results
    print("\n=== ADVISOR SUMMARY ===")
    print(result["summary"])
    
    print("\n=== RECOMMENDATIONS ===")
    for i, rec in enumerate(result["recommendations"], 1):
        print(f"{i}. {rec['college_name']} ({rec['location']})")
        print(f"   Category: {rec['category']}")
        print(f"   Match Score: {rec['match_score']}/100")
        print(f"   Why: {rec['reasoning']}")
        
        if rec.get('application_deadline'):
            print(f"   Deadline: {rec['application_deadline']}")
            
        if rec.get('admission_website'):
            print(f"   Website: {rec['admission_website']}")
        
        if rec.get('scholarship_info'):
            print(f"   Scholarships: {rec['scholarship_info']}")
            if rec.get('scholarship_website'):
                print(f"   Scholarship URL: {rec['scholarship_website']}")
            
        print("-" * 30)

if __name__ == "__main__":
    # Default to 'test_user' if no ID provided
    user_id = sys.argv[1] if len(sys.argv) > 1 else "test_user"
    run_advisor_demo(user_id)