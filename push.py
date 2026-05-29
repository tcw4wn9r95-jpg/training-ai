"""
push.py — On-demand push of the current weekly_plan.json to Garmin Connect.
Triggered by the "Let's do this! 🚀" button via GitHub workflow_dispatch.
Reads the (possibly Coach-edited) plan and pushes it, replacing what's scheduled.
"""
import os
import json
import time
from garminconnect import Garmin
from garmin_push import push_plan_to_garmin


def login_with_retry(email, password, attempts=4):
    """Garmin rate-limits shared GitHub IPs (429). Retry with backoff."""
    delay = 30
    for i in range(1, attempts + 1):
        try:
            client = Garmin(email, password)
            client.login()
            return client
        except Exception as e:
            msg = str(e)
            is_429 = "429" in msg or "rate" in msg.lower() or "too many" in msg.lower()
            if i < attempts and is_429:
                print(f"  Login attempt {i} hit rate limit (429). Waiting {delay}s before retry...")
                time.sleep(delay)
                delay = min(delay * 2, 180)
            elif i < attempts:
                print(f"  Login attempt {i} failed: {msg[:80]}. Retrying in {delay}s...")
                time.sleep(delay)
                delay = min(delay * 2, 180)
            else:
                raise
    raise RuntimeError("Could not log in to Garmin after retries")


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
client = login_with_retry(os.environ["GARMIN_EMAIL"], os.environ["GARMIN_PASSWORD"])
print("Logged in.")

uploaded = push_plan_to_garmin(client, plan_json)

# Update plan status so the dashboard reflects the result
try:
    status = {
        "status": "pushed" if uploaded else "push_failed",
        "uploaded": uploaded,
        "total": len(plan_json),
        "pushed": uploaded > 0,
    }
    with open("plan_status.json", "w") as f:
        json.dump(status, f, indent=2)
    print("Wrote plan_status.json")
except Exception as e:
    print(f"Could not write status: {e}")

print(f"\nDone. {uploaded}/{len(plan_json)} workouts on your Garmin calendar.")
if uploaded:
    print("Sync your Fenix to pull them onto the watch.")
else:
    print("Nothing uploaded — check the errors above.")
