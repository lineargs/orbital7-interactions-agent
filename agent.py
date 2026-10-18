import json
from google import genai
from pydantic import BaseModel
from tools import TOOL_DECLARATIONS, execute_tool

client = genai.Client()  # Reads GEMINI_API_KEY from the environment
MODEL = "gemini-3.8-flash"
MAX_TURNS = 25

SYSTEM_INSTRUCTION = """
You are the on-call Site Reliability Engineer for the Orbital 7 space station.
Bring the station to a safe, stable state and keep the crew alive.

Operating principles:
- Telemetry can be stale or wrong. Confirm anything important with a diagnostic before you rely on it.
- Every action takes time, and oxygen keeps falling while the scrubbers are offline. Do not waste actions.
- Coolant and power are limited. Plan before you spend them.
- Protect life support first, then the systems that keep the station observable, then everything else.
- When an action fails, read the error, work out why, and change your plan. Never repeat a failed action unchanged.
- Never declare the station stable until diagnostics confirm it.
- If there is no safe way forward, escalate to a human instead of guessing.
"""

# Interaction-scoped settings: these do not carry over with previous_interaction_id,
# so every request must send them again.
REQUEST_CONFIG = {
    "model": MODEL,
    "system_instruction": SYSTEM_INSTRUCTION,
    "tools": TOOL_DECLARATIONS,
    "generation_config": {"thinking_summaries": "auto"},
}


def print_thoughts(interaction):
    """Prints the model's thought summaries for this turn."""
    for step in interaction.steps or []:
        if step.type == "thought":
            for block in step.summary or []:
                if block.type == "text":
                    print(f"  💭 {block.text.strip()}")


def run_agent(station, interaction, session, payload_bytes=0):
    """The orchestration loop. Runs until the model completes or something stops it."""
    for turn in range(1, MAX_TURNS + 1):
        usage = interaction.usage
        print(f"\n--- Turn {turn} | {interaction.id} | {interaction.status}")
        print(f"  📦 sent {payload_bytes} bytes | model read "
              f"{getattr(usage, 'total_input_tokens', '?')} input tokens "
              f"({getattr(usage, 'total_cached_tokens', 0) or 0} cached)")

        session["turns"].append({
            "interaction_id": interaction.id, "status": interaction.status,
            "payload_bytes": payload_bytes,
            "input_tokens": getattr(usage, "total_input_tokens", None),
            "cached_tokens": getattr(usage, "total_cached_tokens", None),
            "calls": [],
        })
        print_thoughts(interaction)

        if interaction.status == "completed":
            print(f"\n🛰️ Agent: {interaction.output_text}")
            return interaction

        if interaction.status != "requires_action":
            print(f"\n❌ Interaction ended with status '{interaction.status}'.")
            return interaction

        # The create response contains only this turn's model steps,
        # so every function_call here is new and needs exactly one result.
        results = []
        for call in (s for s in interaction.steps if s.type == "function_call"):
            args = call.arguments or {}
            output, is_error = execute_tool(station, call.name, args)
            icon = "⚠️ " if is_error else "✅"
            print(f"  🤖 {call.name}({json.dumps(args)})")
            print(f"     {icon} {output}")

            session["turns"][-1]["calls"].append(
                {"call_id": call.id, "name": call.name, "arguments": args, "is_error": is_error})
            results.append({
                "type": "function_result",
                "call_id": call.id,
                "name": call.name,
                "result": [{"type": "text", "text": output}],
                "is_error": is_error,
            })

        payload_bytes = len(json.dumps(results).encode())
        interaction = client.interactions.create(
            previous_interaction_id=interaction.id,
            input=results,
            **REQUEST_CONFIG,
        )

    print(f"\n⚠️ Stopped after {MAX_TURNS} turns.")
    return interaction


# ==========================================
# Structured incident report
# ==========================================

class TimelineEntry(BaseModel):
    action: str
    observation: str
    reasoning: str

class FinalState(BaseModel):
    core_temperature_celsius: float
    power_bus_online: bool
    life_support_online: bool
    oxygen_percent: float

class IncidentReport(BaseModel):
    title: str
    root_cause: str
    timeline: list[TimelineEntry]
    final_state: FinalState
    sectors_shed: list[str]
    open_risks: list[str]
    escalated_to_human: bool


def generate_report(previous_interaction_id):
    """Asks the same session for a machine-readable incident report."""
    interaction = client.interactions.create(
        model=MODEL,
        previous_interaction_id=previous_interaction_id,
        input="Write the incident report for this session. Report only what your tool results showed.",
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": IncidentReport.model_json_schema(),
        },
    )
    return interaction, IncidentReport.model_validate_json(interaction.output_text)


def save_session(session, path="session.json"):
    with open(path, "w") as f:
        json.dump(session, f, indent=2)
