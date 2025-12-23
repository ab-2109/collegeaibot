import sys
from pathlib import Path
from .agent import GeneralChatAgent

def run_chat_session(client_id: str):
    # 1. Setup Paths
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent.parent
    data_dir = project_root / "data"

    print(f"--- Initializing General Chat for: {client_id} ---")
    
    # 2. Initialize Agent and Load Context
    agent = GeneralChatAgent()
    print("Loading student file data...")
    context_str = agent.load_student_context(client_id, data_dir)
    
    # Simple check to see if we found data
    if "No data found" in context_str and "intake_profiles" in context_str:
        print(f"⚠️ Warning: Limited data found for {client_id}. Did you run the other agents?")

    print("\n✅ Context Loaded. You can now ask questions about your college journey.")
    print("Type 'exit' or 'quit' to stop.\n")

    # 3. Chat Loop
    chat_history = []
    
    while True:
        try:
            user_input = input(f"You ({client_id}): ").strip()
            if user_input.lower() in ["exit", "quit"]:
                print("Goodbye!")
                break
            
            if not user_input:
                continue

            print("CollegeAI: Thinking...")
            
            response = agent.chat(user_input, context_str, chat_history)
            
            print(f"\nCollegeAI:\n{response}\n")

            # Update history (keep it short for demo purposes)
            chat_history.append({"role": "user", "content": user_input})
            chat_history.append({"role": "assistant", "content": response})
            
            # Keep history manageable
            if len(chat_history) > 10:
                chat_history = chat_history[-10:]

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    user_id = sys.argv[1] if len(sys.argv) > 1 else "demo-user"
    run_chat_session(user_id)