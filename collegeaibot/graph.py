import json
import logging
from pathlib import Path
from typing import TypedDict, Dict, Any, List, Optional

from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

# Import your existing agents
from .intake.agent import IntakeAgent, new_profile
from .advisor.agent import AdvisorAgent
from .cv_review.agent import CVReviewAgent
from .scholarships.agent import ScholarshipsAgent
from .scholarship_prep.agent import ScholarshipPrepAgent
from .general_chat.agent import GeneralChatAgent

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('college_bot_graph')

load_dotenv()

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
    path = Path(f"data/{filename}")
    path.parent.mkdir(exist_ok=True)
    all_data = {}
    if path.exists():
        try:
            with open(path, "r") as f:
                all_data = json.load(f)
        except:
            pass
    all_data[client_id] = data
    with open(path, "w") as f:
        json.dump(all_data, f, indent=2)

def _load_from_disk(filename: str, client_id: str) -> Optional[Dict]:
    path = Path(f"data/{filename}")
    if path.exists():
        try:
            with open(path, "r") as f:
                data = json.load(f)
                return data.get(client_id)
        except:
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
        # Load all context for the chat silently
        return {
            **state,
            "profile": existing_profile,
            "advisor_recommendations": _load_from_disk("advisor_results.json", client_id),
            "cv_feedback": _load_from_disk("cv_review_results.json", client_id),
            "scholarship_list": _load_from_disk("scholarship_recommendations.json", client_id),
            "scholarship_prep_plan": _load_from_disk("prep_suggestions.json", client_id),
            "next_node": "general_chat" # <--- BYPASS SIGNAL
        }
    
    # If no profile, signal to go to intake form
    return {**state, "next_node": "intake_form"}

def intake_form_node(state: GraphState) -> GraphState:
    """
    INTERACTIVE INTAKE:
    Only runs if the user is new (routed here by entry_node).
    """
    client_id = state['client_id']
    logger.info(f"Entering Intake Questionnaire for {client_id}")
    
    print(f"\n--- 📝 Starting Intake for {client_id} ---")
    agent = IntakeAgent()
    profile = new_profile()
    last_user_answer = None
    
    while True:
        response, profile = agent.next_turn(profile, last_user_answer)
        action = response.get("action")
        
        if action == "FINISH":
            print("\n✅ Intake Complete! Proceeding to analysis pipeline...")
            break
        elif action == "END_NOT_US":
            return {**state, "error": "Intake ended: Student not eligible (US only)."}
            
        print(f"\n🤖 CollegeAI: {response.get('question')}")
        last_user_answer = input(f"You: ").strip()
        if last_user_answer.lower() in ["exit", "quit"]:
            return {**state, "error": "User cancelled intake process."}

    _save_to_disk("intake_profiles.json", client_id, profile)
    # No next_node needed here; the graph edge will point to cv_review
    return {**state, "profile": profile}

def cv_review_node(state: GraphState) -> GraphState:
    logger.info("Entering CV Review Node")
    print("--- 📄 Analyzing CV Strategy ---")
    agent = CVReviewAgent()
    dummy_targets = [{"category": "Target Match", "college_name": "Top Tier Universities"}]
    result = agent.analyze_cv(state["profile"], dummy_targets)
    _save_to_disk("cv_review_results.json", state["client_id"], result)
    return {**state, "cv_feedback": result}

def advisor_node(state: GraphState) -> GraphState:
    logger.info("Entering Advisor Node")
    print("--- 🎓 Generating College Recommendations ---")
    agent = AdvisorAgent()
    result = agent.generate_recommendations(state["profile"])
    _save_to_disk("advisor_results.json", state["client_id"], result)
    return {**state, "advisor_recommendations": result}

def scholarships_node(state: GraphState) -> GraphState:
    logger.info("Entering Scholarships Node")
    print("--- 💰 Finding Scholarships ---")
    try:
        agent = ScholarshipsAgent()
        result = agent.find_scholarships(state["profile"], state["advisor_recommendations"])
        _save_to_disk("scholarship_recommendations.json", state["client_id"], result)
        return {**state, "scholarship_list": result}
    except Exception as e:
        logger.warning(f"Scholarship agent failed: {e}")
        return state

def scholarship_prep_node(state: GraphState) -> GraphState:
    logger.info("Entering Scholarship Prep Node")
    print("--- 📝 Creating Prep Plan ---")
    try:
        agent = ScholarshipPrepAgent()
        result = agent.generate_prep_plan(state["profile"], state["scholarship_list"])
        _save_to_disk("prep_suggestions.json", state["client_id"], result)
        return {**state, "scholarship_prep_plan": result}
    except Exception as e:
        logger.warning(f"Scholarship Prep agent failed: {e}")
        return state

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

    context_data = {
        "intake_profiles": state.get("profile"),
        "advisor_results": state.get("advisor_recommendations"),
        "cv_review": state.get("cv_feedback"),
        "scholarships": state.get("scholarship_list"),
        "prep": state.get("scholarship_prep_plan")
    }
    context_str = json.dumps(context_data, indent=2)
    
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
    builder.add_edge("intake_form", "cv_review")
    builder.add_edge("cv_review", "advisor")
    builder.add_edge("advisor", "scholarships")
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