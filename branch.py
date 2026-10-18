import json
from agent import REQUEST_CONFIG, client, run_agent, save_session
from simulator import Station
from tools import execute_tool

# What if the valve that worked had failed as well?
with open("session.json") as f:
    original = json.load(f)

# 1. Find the first turn where a vent_coolant call succeeded
target_index = next(
    i for i, turn in enumerate(original["turns"])
    if any(c["name"] == "vent_coolant" and not c["is_error"] for c in turn["calls"])
)
target_turn = original["turns"][target_index]

# 2. Rebuild the station as it was at that moment by replaying every earlier call.
#    The server holds the conversation. The state of your environment is your job.
station = Station(original["scenario"], original["seed"])
for turn in original["turns"][:target_index]:
    for call in turn["calls"]:
        execute_tool(station, call["name"], call["arguments"])

# 3. Change history: this time the working valve is jammed too
results = []
for call in target_turn["calls"]:
    if call["name"] == "vent_coolant":
        station.jammed_valves.add(call["arguments"]["valve"])
    output, is_error = execute_tool(station, call["name"], call["arguments"])
    print(f"🔀 {call['name']}({json.dumps(call['arguments'])}) -> {output}")
    results.append({"type": "function_result", "call_id": call["call_id"], "name": call["name"],
                    "result": [{"type": "text", "text": output}], "is_error": is_error})

# 4. Continue from the original interaction, with the new results
print(f"\n🔀 Branching from {target_turn['interaction_id']} (turn {target_index + 1} of the original run)")
interaction = client.interactions.create(
    previous_interaction_id=target_turn["interaction_id"],
    input=results,
    **REQUEST_CONFIG,
)

branch = {"scenario": original["scenario"], "seed": original["seed"],
          "branched_from": target_turn["interaction_id"], "turns": []}
interaction = run_agent(station, interaction, branch, payload_bytes=len(json.dumps(results).encode()))
branch["final_interaction_id"] = interaction.id
save_session(branch, "branch.json")

print("\n🔎 SIMULATOR VERDICT (branch)")
print(json.dumps(station.verdict(), indent=2))
