import json
import sys
from google import genai

# A brand-new process: no simulator, no tools, no history.
# All it has is an interaction ID.
client = genai.Client()

if len(sys.argv) > 1:
    interaction_id = sys.argv[1]
else:
    with open("session.json") as f:
        session = json.load(f)
    interaction_id = session.get("report_interaction_id", session["final_interaction_id"])

question = input("Ask the agent about the incident: ")

follow_up = client.interactions.create(
    model="gemini-3.8-flash",
    previous_interaction_id=interaction_id,
    input=question,
)
print(f"\nResumed from {interaction_id}")
print(f"New interaction: {follow_up.id}\n")
print(follow_up.output_text)
