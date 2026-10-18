import argparse
import json
from agent import REQUEST_CONFIG, client, generate_report, run_agent, save_session
from simulator import Station

parser = argparse.ArgumentParser()
parser.add_argument("--scenario", type=int, default=1, help="1, 2 or 3 (random)")
parser.add_argument("--seed", type=int, default=7, help="Seed for scenario 3")
args = parser.parse_args()

station = Station(args.scenario, args.seed)
session = {"scenario": args.scenario, "seed": args.seed, "turns": []}

print("🚨 Orbital 7: main power lost. Starting the on-call agent...")
first_input = "ALERT: Main power lost. Multiple alarms on the station. Restore the station to a safe, stable state."
interaction = client.interactions.create(input=first_input, **REQUEST_CONFIG)
interaction = run_agent(station, interaction, session, payload_bytes=len(first_input.encode()))
session["final_interaction_id"] = interaction.id
save_session(session)

# The agent's claims, as structured data (only possible once the session has completed)
if interaction.status == "completed":
    report_interaction, report = generate_report(interaction.id)
    session["report_interaction_id"] = report_interaction.id
    save_session(session)
    print("\n📝 INCIDENT REPORT (from the agent)")
    print(report.model_dump_json(indent=2))

# Ground truth from the simulator, which the agent never sees
print("\n🔎 SIMULATOR VERDICT (ground truth)")
print(json.dumps(station.verdict(), indent=2))

# What you sent on each turn compared with what the model read
print("\n📊 PAYLOAD VS CONTEXT")
for number, turn in enumerate(session["turns"], 1):
    print(f"Turn {number:>2}: sent {turn['payload_bytes']:>5} bytes | "
          f"model read {turn['input_tokens']} input tokens ({turn['cached_tokens']} cached)")
print("\nSession saved to session.json")
