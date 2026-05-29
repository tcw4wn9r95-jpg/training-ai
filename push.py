"""
push.py — On-demand push of the current weekly_plan.json to Garmin Connect.
Triggered by the "Let's do this! 🚀" button in the dashboard via GitHub
workflow_dispatch. Reads the (possibly Coach-edited) plan and pushes it,
replacing whatever was already scheduled for those days.
"""
import os
import json
from garminconnect import Garmin
from garmin_push import push_plan_to_garmin

print("Loading weekly_plan.json...")
try:
    with open("weekly_plan.json") as f:
        plan_json = json.load(f)
except Exception as e:
    print(f"Could not load plan: {e}")
    raise SystemExit(1)

if not plan_json:
    print("Plan is empty — nothing to push.")
    raise SystemExit(0)

print(f"Plan has {len(plan_json)} sessions.")
print("Connecting to Garmin Connect...")
client = Garmin(os.environ["GARMIN_EMAIL"], os.environ["GARMIN_PASSWORD"])
client.login()
print("Logged in.")

uploaded = push_plan_to_garmin(client, plan_json)

# Update plan status to "pushed" so the dashboard can reflect it
try:
    status = {"status": "pushed", "uploaded": uploaded, "total": len(plan_json)}
    with open("plan_status.json", "w") as f:
        json.dump(status, f, indent=2)
    print("Wrote plan_status.json")
except Exception as e:
    print(f"Could not write status: {e}")

print(f"\nDone. {uploaded}/{len(plan_json)} workouts on your Garmin calendar.")
print("Sync your Fenix to pull them onto the watch.")
