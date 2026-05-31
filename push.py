"""
push.py — On-demand push of the current plan to Garmin Connect.
Triggered by the "Let's do this! 🚀" button via GitHub workflow_dispatch.

Pushes:
  - Week 1 (full step detail) from weekly_plan.json  — reflects any coach edits
  - Weeks 2-4 (outline sessions) from plan_block.json — shows the full block on calendar
"""
import os
import json
import time
from datetime import date, timedelta
from garminconnect import Garmin
from garmin_push import push_plan_to_garmin

DAY_OFFSETS = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
    "Friday": 4, "Saturday": 5, "Sunday": 6,
}


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


def outline_sessions_for_week(block_week):
    """Build session list for an outline week with dates derived from week_of + day offset."""
    week_of = block_week.get("week_of", "")
    if not week_of:
        return []
    base = date.fromisoformat(week_of)
    result = []
    for s in block_week.get("sessions", []):
        day = s.get("day", "")
        offset = DAY_OFFSETS.get(day)
        if offset is None:
            continue  # drop sessions with invalid day names
        session = dict(s)
        session["date"] = (base + timedelta(days=offset)).isoformat()
        result.append(session)
    return result


print("Loading weekly_plan.json (week 1 — full detail)...")
try:
    with open("weekly_plan.json") as f:
        plan_json = json.load(f)
except Exception as e:
    print(f"Could not load plan: {e}")
    raise SystemExit(1)

if not plan_json:
    print("Plan is empty — nothing to push.")
    raise SystemExit(0)

print(f"Week 1: {len(plan_json)} sessions.")

# Load weeks 2-4 outline sessions from plan_block.json
outline_sessions = []
try:
    with open("plan_block.json") as f:
        plan_block = json.load(f)
    # Identify the detailed (week 1) week_of so we don't double-push it
    detailed_week_of = next((wk["week_of"] for wk in plan_block if wk.get("detailed")), None)
    if not detailed_week_of and plan_json:
        detailed_week_of = plan_json[0].get("date", "")[:10]
    for wk in plan_block:
        if wk.get("week_of") == detailed_week_of:
            continue  # skip week 1 — already in weekly_plan.json
        sessions = outline_sessions_for_week(wk)
        outline_sessions.extend(sessions)
    print(f"Weeks 2-4: {len(outline_sessions)} outline sessions.")
except Exception as e:
    print(f"Could not load plan_block.json (skipping weeks 2-4): {e}")

all_sessions = plan_json + outline_sessions
print(f"Total to push: {len(all_sessions)} sessions.")
print("Connecting to Garmin Connect...")
client = login_with_retry(os.environ["GARMIN_EMAIL"], os.environ["GARMIN_PASSWORD"])
print("Logged in.")

uploaded = push_plan_to_garmin(client, all_sessions)

try:
    status = {
        "status": "pushed" if uploaded else "push_failed",
        "uploaded": uploaded,
        "total": len(all_sessions),
        "pushed": uploaded > 0,
    }
    with open("plan_status.json", "w") as f:
        json.dump(status, f, indent=2)
    print("Wrote plan_status.json")
except Exception as e:
    print(f"Could not write status: {e}")

print(f"\nDone. {uploaded}/{len(all_sessions)} workouts on your Garmin calendar.")
if uploaded:
    print("Sync your Fenix to pull them onto the watch.")
else:
    print("Nothing uploaded — check the errors above.")
