import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

# Import your existing agents
from .intake.agent import IntakeAgent, apply_patch_ops, new_profile
from .advisor.agent import AdvisorAgent
from .cv_review.agent import CVReviewAgent
from .scholarships.agent import ScholarshipsAgent
from .scholarship_prep.agent import ScholarshipPrepAgent
from .general_chat.agent import GeneralChatAgent

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('college_bot_graph')

load_dotenv()

DATA_DIR = Path("data")

# --- 1. Define Graph State ---
class GraphState(TypedDict):
    client_id: str
    user_input: str
    profile: Optional[Dict[str, Any]]
    advisor_recommendations: Optional[Dict[str, Any]]
    cv_feedback: Optional[Dict[str, Any]]
    scholarship_list: Optional[Dict[str, Any]]
    scholarship_prep_plan: Optional[Dict[str, Any]]
    chat_history: List[Dict[str, str]]
    next_node: Optional[str]
    is_complete: bool
    error: Optional[str]

# --- 2. Helper Functions ---
def _save_to_disk(filename: str, client_id: str, data: Any):
    path = DATA_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    all_data: Dict[str, Any] = {}
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                all_data = json.load(f)
        except Exception:
            all_data = {}
    all_data[client_id] = data
    with path.open("w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

def _load_from_disk(filename: str, client_id: str) -> Optional[Dict]:
    path = DATA_DIR / filename
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get(client_id)
        except Exception:
            return None
    return None

# --- 3. Define Nodes ---

def entry_node(state: GraphState) -> GraphState:
    """
    ROUTER NODE:
    Checks if the user profile exists.
    - If YES: Loads data and routes directly to General Chat.
    - If NO: Routes to Intake Form.
    """
    client_id = state['client_id']
    # logger.info(f"Checking profile for {client_id}") 
    
    existing_profile = _load_from_disk("intake_profiles.json", client_id)

    if existing_profile:
        # Existing user: go straight to chat (chat loads context from disk).
        return {**state, "profile": existing_profile, "next_node": "general_chat"}
    
    # If no profile, signal to go to intake form
    return {**state, "next_node": "intake_form"}

def intake_form_node(state: GraphState) -> GraphState:
    """
    INTERACTIVE INTAKE:
    Only runs if the user is new (routed here by entry_node).
    """
    client_id = state['client_id']
    logger.info(f"Entering Intake Questionnaire for {client_id}")
    
    print(f"\n--- Starting Intake for {client_id} ---")
    agent = IntakeAgent()
    profile = new_profile()
    last_user_answer = None
    last_question_id = None
    
    while True:
        response, profile = agent.next_turn(profile, last_user_answer, last_question_id)
        action = response.get("action")
        
        if action == "FINISH":
            print("\nIntake complete! Proceeding to analysis pipeline...")
            break
        elif action == "END_NOT_US":
            return {**state, "error": "Intake ended: Student not eligible (US only)."}

        q = response.get("question")
        if not isinstance(q, dict) or not q.get("text"):
            return {**state, "error": "Intake error: missing question."}

        print(f"\nCollegeAI: {q['text']}")
        if q.get("options"):
            print("Options: " + ", ".join([str(x) for x in q.get("options") or []]))

        last_question_id = q.get("id")
        last_user_answer = input("You: ").strip()
        if last_user_answer.lower() in ["exit", "quit"]:
            return {**state, "error": "User cancelled intake process."}

    _save_to_disk("intake_profiles.json", client_id, profile)
    # No next_node needed here; the graph edge will point to cv_review
    return {**state, "profile": profile}

def cv_review_node(state: GraphState) -> GraphState:
    logger.info("Entering CV Review Node")
    print("--- CV Strategy ---")
    agent = CVReviewAgent()
    advisor_blob = state.get("advisor_recommendations") or {}
    advisor_recs = advisor_blob.get("recommendations") if isinstance(advisor_blob, dict) else []
    if not isinstance(advisor_recs, list):
        advisor_recs = []
    result = agent.analyze_cv(state["profile"], advisor_recs)
    _save_to_disk("cv_review_results.json", state["client_id"], result)

    # Print after advisor results (pipeline order is advisor -> cv_review).
    if isinstance(result, dict):
        summary = result.get("strategic_summary")
        if summary:
            print("\nCV Summary:")
            print(str(summary))
        improvements = result.get("improvements") or []
        if isinstance(improvements, list) and improvements:
            print("\nTop CV Improvements:")
            for i, imp in enumerate(improvements[:6], 1):
                if isinstance(imp, dict):
                    title = imp.get("title") or "Improvement"
                    detail = imp.get("details") or imp.get("description") or ""
                    print(f"{i}. {title} - {detail}".strip())
    return {**state, "cv_feedback": result}

def advisor_node(state: GraphState) -> GraphState:
    logger.info("Entering Advisor Node")
    print("--- College Recommendations ---")
    agent = AdvisorAgent()
    result = agent.generate_recommendations(state["profile"])
    _save_to_disk("advisor_results.json", state["client_id"], result)

    # Print recommendations first (user requested).
    if isinstance(result, dict):
        summary = result.get("summary")
        if summary:
            print("\nSummary:")
            print(str(summary))
        recs = result.get("recommendations") or []
        if isinstance(recs, list) and recs:
            print("\nRecommended Colleges:")
            for i, r in enumerate(recs, 1):
                if not isinstance(r, dict):
                    continue
                name = r.get("college_name") or "(unknown)"
                cat = r.get("category") or ""
                score = r.get("match_score")
                loc = r.get("location") or ""
                line = f"{i}. {name}"
                meta = " | ".join([x for x in [str(cat) if cat else "", f"score={score}" if score is not None else "", loc] if x])
                if meta:
                    line += f" ({meta})"
                print(line)
    return {**state, "advisor_recommendations": result}

def scholarships_node(state: GraphState) -> GraphState:
    logger.info("Entering Scholarships Node")
    print("--- Scholarships ---")
    try:
        agent = ScholarshipsAgent()
        client_id = state["client_id"]

        intake_profile = state.get("profile") or {}
        scholarships_profile = _load_from_disk("scholarships_profiles.json", client_id) or {}
        if not isinstance(intake_profile, dict):
            intake_profile = {}
        if not isinstance(scholarships_profile, dict):
            scholarships_profile = {}

        merged: Dict[str, Any] = dict(intake_profile)
        merged.update(scholarships_profile)

        last_answer: Optional[str] = None
        last_question_id: Optional[str] = None

        for _ in range(12):
            response, merged = agent.next_turn(
                profile=merged,
                last_user_answer=last_answer,
                last_question_id=last_question_id,
                advisor_data=state.get("advisor_recommendations"),
            )

            patch_ops = response.get("profile_patch") or []
            if isinstance(patch_ops, list) and patch_ops:
                apply_patch_ops(scholarships_profile, patch_ops)
                _save_to_disk("scholarships_profiles.json", client_id, scholarships_profile)

            action = response.get("action")
            if action == "ASK":
                q = response.get("question")
                if not isinstance(q, dict) or not q.get("text"):
                    return {**state, "error": "Scholarships error: missing question."}
                print(f"\nCollegeAI (scholarships): {q['text']}")
                if q.get("options"):
                    print("Options: " + ", ".join([str(x) for x in q.get("options") or []]))
                last_question_id = q.get("id")
                last_answer = input("You: ").strip()
                continue

            if action == "END_NOT_US":
                return {**state, "error": "Scholarships ended: Student not eligible (US only)."}

            if action == "CLARIFY":
                return {**state, "error": f"Scholarships: {response.get('note_to_user', '')}"}

            if action == "RECOMMEND":
                recs = response.get("recommendations") or []
                result = {
                    "recommendations": recs,
                    "note_to_user": response.get("note_to_user", ""),
                }
                _save_to_disk("scholarship_recommendations.json", client_id, result)
                return {**state, "scholarship_list": result}

            return {**state, "error": f"Scholarships: unexpected action {action!r}"}

        return {**state, "error": "Scholarships: too many turns without completion."}
    except Exception as e:
        logger.warning(f"Scholarship agent failed: {e}")
        return {**state, "error": f"Scholarship agent failed: {str(e)[:160]}"}

def scholarship_prep_node(state: GraphState) -> GraphState:
    logger.info("Entering Scholarship Prep Node")
    print("--- Scholarship Prep Plan ---")
    try:
        agent = ScholarshipPrepAgent()
        client_id = state["client_id"]

        intake_profile = state.get("profile") or {}
        scholarships_profile = _load_from_disk("scholarships_profiles.json", client_id) or {}
        if not isinstance(intake_profile, dict):
            intake_profile = {}
        if not isinstance(scholarships_profile, dict):
            scholarships_profile = {}

        merged: Dict[str, Any] = dict(intake_profile)
        merged.update(scholarships_profile)

        scholarship_blob = state.get("scholarship_list") or {}
        scholarship_recs: List[Dict[str, Any]] = []
        if isinstance(scholarship_blob, dict):
            scholarship_recs = scholarship_blob.get("recommendations") or []
        if not isinstance(scholarship_recs, list):
            scholarship_recs = []

        last_answer: Optional[str] = None
        last_question_id: Optional[str] = None

        for _ in range(12):
            response, merged = agent.next_turn(
                profile=merged,
                last_user_answer=last_answer,
                last_question_id=last_question_id,
                scholarship_recommendations=scholarship_recs,
            )

            patch_ops = response.get("profile_patch") or []
            if isinstance(patch_ops, list) and patch_ops:
                apply_patch_ops(intake_profile, patch_ops)
                _save_to_disk("intake_profiles.json", client_id, intake_profile)

            action = response.get("action")
            if action == "ASK":
                q = response.get("question")
                if not isinstance(q, dict) or not q.get("text"):
                    return {**state, "error": "Prep error: missing question."}
                print(f"\nCollegeAI (prep): {q['text']}")
                if q.get("options"):
                    print("Options: " + ", ".join([str(x) for x in q.get("options") or []]))
                last_question_id = q.get("id")
                last_answer = input("You: ").strip()
                continue

            if action == "CLARIFY":
                return {**state, "error": f"Prep: {response.get('note_to_user', '')}"}

            if action == "SUGGEST":
                result = {
                    "summary": response.get("summary"),
                    "suggestions": response.get("suggestions") or [],
                }
                _save_to_disk("prep_suggestions.json", client_id, result)
                return {**state, "scholarship_prep_plan": result}

            if action == "END":
                result = {
                    "summary": response.get("note_to_user", ""),
                    "suggestions": [],
                }
                _save_to_disk("prep_suggestions.json", client_id, result)
                return {**state, "scholarship_prep_plan": result}

            return {**state, "error": f"Prep: unexpected action {action!r}"}

        return {**state, "error": "Prep: too many turns without completion."}
    except Exception as e:
        logger.warning(f"Scholarship Prep agent failed: {e}")
        return {**state, "error": f"Scholarship Prep agent failed: {str(e)[:160]}"}

def general_chat_node(state: GraphState) -> GraphState:
    logger.info("Entering General Chat Node")
    agent = GeneralChatAgent()
    
    query = state["user_input"]
    
    # --- SYSTEM PROMPT HANDLING ---
    if query == "START_INTAKE":
        query = "I have just completed my profile intake. Please analyze my data, welcome me, and suggest next steps."
    elif query == "EXISTING_USER_LOGIN":
        query = "I am logging back in. Please welcome me back briefly. Do NOT summarize my profile. Just ask how you can help me today."
    # ------------------------------

    context_str = agent.load_student_context(state["client_id"], DATA_DIR)
    
    response = agent.chat(query, context_str, state.get("chat_history", []))
    
    new_history = state.get("chat_history", []) + [
        {"role": "user", "content": query},
        {"role": "assistant", "content": response}
    ]
    return {**state, "chat_history": new_history, "is_complete": True}

# --- 4. Build the Graph ---

def route_entry(state: GraphState) -> str:
    """Determines where to go from the Entry Node"""
    return state.get("next_node", "intake_form")

def build_college_graph() -> StateGraph:
    builder = StateGraph(GraphState)
    
    # Add Nodes
    builder.add_node("entry", entry_node)          # Router
    builder.add_node("intake_form", intake_form_node) # Questionnaire
    builder.add_node("cv_review", cv_review_node)
    builder.add_node("advisor", advisor_node)
    builder.add_node("scholarships", scholarships_node)
    builder.add_node("scholarship_prep", scholarship_prep_node)
    builder.add_node("general_chat", general_chat_node)
    
    # Set Entry Point
    builder.set_entry_point("entry")
    
    # Conditional Edge from Entry
    builder.add_conditional_edges(
        "entry",
        route_entry,
        {
            "general_chat": "general_chat", # Bypass everything
            "intake_form": "intake_form"    # Start new user flow
        }
    )
    
    # Standard Pipeline Edges
    # Advisor must run before CV review (CV uses reach/target colleges).
    builder.add_edge("intake_form", "advisor")
    builder.add_edge("advisor", "cv_review")
    builder.add_edge("cv_review", "scholarships")
    builder.add_edge("scholarships", "scholarship_prep")
    builder.add_edge("scholarship_prep", "general_chat")
    builder.add_edge("general_chat", END)
    
    return builder.compile()

# --- 5. Execution Helper ---

def run_pipeline(client_id: str = None):
    # 1. Get User ID
    if not client_id:
        client_id = input("Enter your User ID (e.g., 'john_doe'): ").strip()
        if not client_id:
            print("User ID is required.")
            return

    # 2. Determine Initial State
    existing_profile = _load_from_disk("intake_profiles.json", client_id)
    chat_history = []
    
    if existing_profile:
        print(f"\n--- Session Started for {client_id} ---")
        initial_input = "EXISTING_USER_LOGIN"
    else:
        print(f"\n🆕 New user detected: {client_id}")
        print("We need to build your profile first.")
        input("Press Enter to start the Intake process...")
        initial_input = "START_INTAKE"

    # 3. Run Graph Automatically (First Turn)
    initial_state = {
        "client_id": client_id,
        "user_input": initial_input,
        "chat_history": chat_history,
        "profile": None,
        "advisor_recommendations": None,
        "cv_feedback": None,
        "scholarship_list": None,
        "scholarship_prep_plan": None,
        "is_complete": False,
        "error": None,
        "next_node": None
    }
    
    graph = build_college_graph()
    final_state = graph.invoke(initial_state)
    
    if final_state.get("error"):
        print(f"❌ Error: {final_state['error']}")
        return

    # 4. Print Bot's Opening Message
    chat_history = final_state.get("chat_history", [])
    if chat_history:
        last_response = chat_history[-1]["content"]
        print(f"\n🤖 CollegeAI: {last_response}\n")
    
    # 5. Interactive Loop
    while True:
        user_input = input(f"You ({client_id}): ").strip()
        
        if user_input.lower() in ['exit', 'quit']:
            print("Goodbye!")
            break
            
        if not user_input:
            continue

        # Prepare state for next turn
        next_state = {
            "client_id": client_id,
            "user_input": user_input,
            "chat_history": chat_history,
            "profile": None, 
            "advisor_recommendations": None,
            "cv_feedback": None,
            "scholarship_list": None,
            "scholarship_prep_plan": None,
            "is_complete": False,
            "error": None,
            "next_node": None
        }
        
        final_state = graph.invoke(next_state)
        
        if final_state.get("error"):
            print(f"❌ Error: {final_state['error']}")
            break 
        
        chat_history = final_state.get("chat_history", [])
        if chat_history:
            last_response = chat_history[-1]["content"]
            print(f"\n🤖 CollegeAI: {last_response}\n")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        run_pipeline(sys.argv[1])
    else:
        run_pipeline()