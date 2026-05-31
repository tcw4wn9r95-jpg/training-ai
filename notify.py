import json, os, sys, tempfile
from datetime import date, timedelta

try:
    from pywebpush import webpush, WebPushException
except ImportError:
    print("pywebpush not installed — run: pip install pywebpush")
    sys.exit(1)

VAPID_PRIVATE_KEY_PEM = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS = {"sub": "mailto:bot@coachclaudio.local"}

SPORT_LABELS = {
    "running": "Run", "cycling": "Ride", "cycling_indoor": "Ride",
    "strength": "Strength", "swimming": "Swim", "yoga": "Yoga",
    "hiking": "Hike", "walking": "Walk", "rowing": "Row",
    "elliptical": "Elliptical", "tennis": "Tennis",
    "skiing": "Ski", "soccer": "Soccer", "boxing": "Boxing",
}

def get_tomorrow_sessions():
    tomorrow = date.today() + timedelta(days=1)
    tomorrow_name = tomorrow.strftime("%A")
    tomorrow_iso  = tomorrow.isoformat()
    try:
        with open("weekly_plan.json") as f:
            plan = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return [], tomorrow_name
    return [s for s in plan if s.get("day") == tomorrow_name or s.get("date") == tomorrow_iso], tomorrow_name

def format_notification(sessions, day_name):
    if not sessions:
        return (
            f"Coach Claudio — {day_name}",
            "Rest day tomorrow. Recovery is training too 💤"
        )
    parts = []
    total_tss = 0
    for s in sessions:
        sport = SPORT_LABELS.get(s.get("sport", ""), s.get("sport", "Session").capitalize())
        dur = round(s.get("total_duration_secs", 0) / 60) if s.get("total_duration_secs") else None
        name = s.get("name") or sport
        total_tss += s.get("planned_tss") or 0
        parts.append(f"{name} ({dur} min)" if dur else name)
    body = " · ".join(parts)
    if total_tss:
        body += f"  ·  {round(total_tss)} TSS"
    return f"Coach Claudio — {day_name}", body

def main():
    if not VAPID_PRIVATE_KEY_PEM:
        print("VAPID_PRIVATE_KEY not set")
        sys.exit(1)

    try:
        with open("push_subscriptions.json") as f:
            subs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        subs = []

    if not subs:
        print("No push subscriptions — nothing to send")
        return

    sessions, day_name = get_tomorrow_sessions()
    title, body = format_notification(sessions, day_name)
    print(f"Sending: {title}\n         {body}")

    # Write VAPID private key PEM to a temp file for pywebpush
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
        f.write(VAPID_PRIVATE_KEY_PEM)
        pem_path = f.name

    payload = json.dumps({"title": title, "body": body})
    failed = set()
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=pem_path,
                vapid_claims=VAPID_CLAIMS,
            )
            print(f"  ✓ {sub['endpoint'][:60]}…")
        except WebPushException as e:
            status = e.response.status_code if e.response else None
            if status in (404, 410):
                print(f"  ✗ expired ({status}), removing")
                failed.add(sub["endpoint"])
            else:
                print(f"  ✗ failed: {e}")
        except Exception as e:
            print(f"  ✗ error: {e}")

    os.unlink(pem_path)

    if failed:
        subs = [s for s in subs if s["endpoint"] not in failed]
        with open("push_subscriptions.json", "w") as f:
            json.dump(subs, f, indent=2)
        print(f"Removed {len(failed)} expired subscription(s)")

main()
