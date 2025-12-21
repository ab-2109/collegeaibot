# collegeaibot

This repository currently contains a **questionnaire / intake agent** for
US college applicants. The intake agent is designed to be a node in a
larger agentic pipeline (for example, a LangGraph workflow) that will
feed a downstream **college recommendation agent**.

## Components

- `collegeaibot/intake/schemas.py`  
  Profile template (`PROFILE_TEMPLATE`) and JSON schema (`NEXT_TURN_SCHEMA`) for
  the next-turn object.
- `collegeaibot/intake/prompts.py`  
  System instructions (`SYSTEM_INSTRUCTIONS`) describing the interview
  strategy and hard rules.
- `collegeaibot/intake/client.py`  
  OpenAI client + model configuration.
- `collegeaibot/intake/agent.py`  
  `IntakeAgent` class, `deep_merge` helper, and `new_profile()` factory.
- `collegeaibot/intake/storage.py`  
  Simple profile stores: in-memory and JSON-file-backed. These are meant
  to be swapped for a MongoDB store later without changing the agent.
- `collegeaibot/intake/cli_demo.py`  
  Minimal CLI to exercise the intake flow end-to-end.

## Running the intake CLI

1. Install dependencies (already done in your environment):

```bash
pip install -r requirements.txt
```

2. Set your OpenAI API key (and optionally model):

```bash
export OPENAI_API_KEY="YOUR_API_KEY"
# Optional: override default model (defaults to "gpt-5")
export COLLEGEAIBOT_MODEL="gpt-5"
```

3. Run the demo:

```bash
python -m collegeaibot.intake.cli_demo
```

The CLI will:

- Maintain a JSON file at `data/intake_profiles.json` with one profile per
  `client_id`.
- Ask exactly one question per turn, updating the profile via `profile_patch`.
- Stop when the model returns `action` = `FINISH` or `END_NOT_US`.

## Using this as a LangGraph node (high level)

- Treat the `profile` dict as part of your graph state.
- At each step, call `IntakeAgent.next_turn(profile, last_user_answer)`.
- Merge the returned `profile_patch` into your state (or delegate to a
  `ProfileStore` implementation such as MongoDB in the future).
- When `action` is `FINISH`, hand off the final profile to the
  recommendation agent node.
