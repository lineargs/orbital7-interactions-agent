# Orbital 7 — Stateful SRE Agent with the Gemini Interactions API

Reference implementation for the interactive codelab: **[Build Stateful Agentic Apps with the Gemini Interactions API](https://lineargs.dev/codelabs/stateful-agents-gemini-interactions-api)** on [lineargs.dev](https://lineargs.dev/codelabs).

In this project, you build an autonomous on-call Site Reliability Engineer (SRE) agent for **Orbital 7**, an ageing space station that has just lost main power. Using the stateful **Gemini Interactions API** (`client.interactions`) and `gemini-3.8-flash`, the agent diagnoses hidden hardware faults, recovers from jammed coolant valves and overloaded power configurations, generates a schema-validated incident report, resumes sessions across processes, and branches timelines to test alternate failure modes.

---

## What This Repository Demonstrates

1. **Server-Side Conversation State (`previous_interaction_id`):**
   Every turn sends only the newly executed tool results (a few hundred bytes) and `previous_interaction_id`. No local `messages = []` history array is maintained in Python.
2. **Turn-Scoped Configuration (`REQUEST_CONFIG`):**
   Demonstrates the separation between conversation history (stored on the server) and per-interaction settings (`model`, `system_instruction`, `tools`, and `generation_config`).
3. **Multi-Turn Function Calling & Error Recovery (`requires_action` → `function_result`):**
   Exposes capability-oriented JSON Schema tools (`TOOL_DECLARATIONS`) and converts simulator exceptions (`RuntimeError`, `ValueError`) into `"is_error": True` tool observations so the model adapts its plan instead of crashing.
4. **Observable Reasoning (`thinking_summaries: "auto"`):**
   Extracts and prints `"thought"` steps (`💭`) from `interaction.steps` before executing tool calls.
5. **Structured Output Chained to a Session (`IncidentReport`):**
   Uses Pydantic's `model_json_schema()` with `response_format` on a follow-up turn to produce a strictly typed post-incident report, and compares the agent's claims against the simulator's ground-truth `verdict()`.
6. **Cross-Process Session Resumption (`resume.py`):**
   Continues a completed session from a brand-new Python process with zero local state or tool imports, using only the stored `interaction_id`.
7. **Timeline Branching (`branch.py`):**
   Rewinds to an earlier turn in `session.json`, replays local `Station` state up to that point, jams the remaining coolant valve, and forks a new timeline from that turn's `interaction_id`.

---

## Repository Structure

```text
orbital7-agent/
├── simulator.py      # Orbital 7 station simulator, fault scenarios, and ground-truth verdict()
├── tools.py          # JSON Schema tool declarations (TOOL_DECLARATIONS) and execute_tool()
├── agent.py          # Gemini client, REQUEST_CONFIG, stateful loop (run_agent), and IncidentReport
├── main.py           # Runs an incident scenario, generates the report, and prints token metrics
├── resume.py         # Resumes a saved session from a separate process using only its interaction ID
├── branch.py         # Rewinds to an earlier turn, jams the working valve, and forks the timeline
└── requirements.txt  # Python dependencies (google-genai >= 2.3.0, pydantic >= 2.0.0)
```

---

## Quickstart

### 1. Prerequisites

- Python 3.10+
- A Gemini API key (`GEMINI_API_KEY`)

Install the required dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Export your Gemini API key:

```bash
export GEMINI_API_KEY="your_api_key_here"
```

### 2. Run the On-Call Agent (`main.py`)

Run **Scenario 1 (Thermal Trip)**, where Valve A is jammed and the pre-blackout power allocation exceeds the reactor's 70 MW capacity:

```bash
python main.py --scenario 1
```

Run **Scenario 2 (Ghost Sensor)**, where Valve B is jammed, reactor capacity is 60 MW, and the oxygen sensor is stuck at `97.0%` while the `life_support` diagnostic self-test fails and CO2 rises:

```bash
python main.py --scenario 2
```

Run **Scenario 3 (Random Faults)** with a reproducible seed:

```bash
python main.py --scenario 3 --seed 11
python main.py --scenario 3 --seed 42
```

Each run saves its turn-by-turn audit trail and interaction IDs to `session.json`.

### 3. Resume the Session from a New Process (`resume.py`)

In a separate terminal window (with `GEMINI_API_KEY` exported), ask follow-up questions about the incident. `resume.py` imports neither the simulator nor the tools—it continues directly from the interaction ID saved in `session.json`:

```bash
python resume.py
```

Or pass any specific interaction ID directly:

```bash
python resume.py <interaction_id>
```

### 4. Branch the Timeline (`branch.py`)

Rewind to the first turn where `vent_coolant` succeeded, rebuild the station's state up to that moment, jam the working valve as well, and fork the conversation from that turn's `interaction_id`:

```bash
python branch.py
```

With both coolant valves jammed, the agent recognises that the reactor cannot be cooled safely and invokes `escalate_to_human`. The forked run is saved to `branch.json` while `session.json` remains unchanged.

---

## License

MIT
