import os
import json
import anthropic
from datetime import date, timedelta
from garminconnect import Garmin

# ── Load profile and availability ────────────────────────────────────────────
with open("profile.json") as f:
    profile = json.load(f)

with open("availability.json") as f:
    availability = json.load(f)

# Support both old format (available_days list) and new format (days dict with hours)
availability_notes = availability.get("notes", "")
days_data = availability.get("days", {})

if days_data:
    # New format: {"Monday": {"available": true, "hours": 1.5}, ...}
    available_days = [d for d, v in days_data.items() if v.get("available")]
    hours_per_day = {d: v.get("hours", 1.0) for d, v in days_data.items() if v.get("available")}
else:
    # Old format fallback
    available_days = availability.get("available_days", ["Monday","Wednesday","Thursday","Saturday","Sunday"])
    hours_per_day = {d: 1.0 for d in available_days}

if not available_days:
    available_days = ["Monday", "Wednesday", "Thursday", "Saturday", "Sunday"]
    hours_per_day = {d: 1.0 for d in available_days}

# ── Fetch Garmin data ─────────────────────────────────────────────────────────
print("Connecting to Garmin Connect...")
client = Garmin(os.environ["GARMIN_EMAIL"], os.environ["GARMIN_PASSWORD"])
client.login()
print("Logged in.")

end_date = date.today()
start_date = end_date - timedelta(days=42)  # 6 weeks of history

activities = client.get_activities_by_date(
    start_date.isoformat(), end_date.isoformat()
)
print(f"Found {len(activities)} activities in the last 6 weeks.")

# ── Parse activities ──────────────────────────────────────────────────────────
workouts = []
for a in activities:
    sport_raw = a.get("activityType", {}).get("typeKey", "unknown")
    sport_map = {
        "running": "running",
        "cycling": "cycling",
        "road_biking": "cycling",
        "indoor_cycling": "cycling_indoor",
        "strength_training": "strength",
        "fitness_equipment": "strength",
    }
    sport = sport_map.get(sport_raw, sport_raw)

    duration_sec = a.get("duration", 0)
    duration_min = round(duration_sec / 60, 1)
    distance_m = a.get("distance", 0)
    distance_km = round(distance_m / 1000, 2) if distance_m else 0
    avg_hr = a.get("averageHR", 0)
    avg_power = a.get("avgPower", 0)

    avg_pace = None
    if sport == "running" and distance_km > 0 and duration_min > 0:
        avg_pace = round(duration_min / distance_km, 2)

    workouts.append({
        "date": a.get("startTimeLocal", "")[:10],
        "sport": sport,
        "duration_min": duration_min,
        "distance_km": distance_km,
        "avg_hr": avg_hr,
        "max_hr": a.get("maxHR", 0),
        "avg_pace_min_km": avg_pace,
        "avg_power_watts": avg_power,
        "calories": a.get("calories", 0),
    })

# Save workout history
with open("workouts.json", "w") as f:
    json.dump(workouts, f, indent=2)
print("Workout history saved.")

# ── Build next week date labels ───────────────────────────────────────────────
today = date.today()
days_until_monday = (7 - today.weekday()) % 7 or 7
next_monday = today + timedelta(days=days_until_monday)
week_days = []
day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
for i, name in enumerate(day_names):
    week_days.append({
        "name": name,
        "date": (next_monday + timedelta(days=i)).strftime("%d %b"),
        "available": name in available_days
    })

week_schedule = "\n".join(
    f"  {d['name']} {d['date']}: "
    + ("✅ AVAILABLE — " + str(hours_per_day.get(d['name'], 1.0)) + "h max" if d['available'] else "❌ REST DAY")
    for d in week_days
)

# ── Call Claude ───────────────────────────────────────────────────────────────
print("Calling Claude for training plan...")
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

prompt = f"""You are Diego's personal trainer. Build a detailed weekly training plan.

## ATHLETE PROFILE
- Name: Diego
- Device: Garmin Fenix
- Resting HR: {profile['running']['resting_hr']} bpm | Max HR: {profile['running']['max_hr']} bpm

## RUNNING ZONES
- Z1 Recovery:  < 145 bpm  |  pace > 7:00/km
- Z2 Aerobic:   146–162 bpm  |  pace 6:15–6:45/km
- Z3 Tempo:     163–172 bpm  |  pace 5:30–6:00/km
- Z4 Threshold: 173–181 bpm  |  pace 4:45–5:20/km
- Z5 VO2max:    > 181 bpm  |  pace < 4:30/km

## CYCLING ZONES
- Z1 Recovery:  < 145 bpm  |  power < 106W  (< 55% FTP)
- Z2 Aerobic:   146–162 bpm  |  power 106–141W  (56–75% FTP)
- Z3 Tempo:     163–172 bpm  |  power 142–168W  (76–90% FTP)
- Z4 Threshold: 173–181 bpm  |  power 169–195W  (91–105% FTP)
- Z5 VO2max:    > 181 bpm  |  power 196–239W  (106–120% FTP)
- Outdoor cycling: HR targets only (no power meter outdoors)
- Indoor cycling: use power targets

## STRENGTH EQUIPMENT
- TRX, resistance bands
- Dumbbells: 6kg, 11kg, 16kg, 22kg (no gym, home only)

## NEXT WEEK AVAILABILITY
{week_schedule}
{f"Notes from Diego: {availability_notes}" if availability_notes else ""}

## LAST 6 WEEKS OF TRAINING DATA
{json.dumps(workouts, indent=2)}

## INSTRUCTIONS
Build a plan ONLY for the available days above. Rest days must stay as rest.
Respect the available hours strictly — do not plan a session longer than the available hours for that day.
Longer availability = longer or harder session. Shorter = shorter, more focused.
For each training day provide EXACTLY this structure:

### [DAY NAME] [DATE] — [Session type]
**Sport:** [Running / Cycling indoor / Cycling outdoor / Strength]
**Total duration:** [X min]
**Session goal:** [one sentence on the purpose]

**Warm-up:** [duration + HR zone + pace or power target]
**Main set:**
- [Interval 1: duration/distance + HR zone + pace or power + specific Garmin alert to set]
- [Interval 2: ...]
- [Rest between: duration + target HR]
**Cool-down:** [duration + HR zone + pace or power target]

**RPE target:** [X/10]
**Key Garmin settings:** [exactly what alerts to set on the Fenix]
**Coaching note:** [1-2 sentences of practical advice]

---

After all days, add:

## WEEK SUMMARY
**Total planned load:** [TSS estimate]
**Weekly volume:** [running km] running | [cycling km] cycling | [strength sessions] strength sessions
**Focus this week:** [one sentence]

## INSIGHTS FROM YOUR RECENT DATA
[3 bullet points with specific observations from the workout data above — reference actual dates and numbers]

## WATCH OUT FOR
[1-2 specific warnings based on the data — e.g. overtraining, missing recovery, imbalances]
"""

message = claude.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=4000,
    messages=[{"role": "user", "content": prompt}]
)

plan_text = message.content[0].text
print("Plan received from Claude.")

# ── Save plan ─────────────────────────────────────────────────────────────────
week_label = next_monday.strftime("%Y-%m-%d")
output = f"# Training Plan — Week of {next_monday.strftime('%d %B %Y')}\n\n"
output += f"**Generated:** {date.today().strftime('%d %B %Y')}  \n"
output += f"**Available days:** {', '.join(available_days)}  \n\n"
output += "---\n\n"
output += plan_text

with open("weekly_plan.md", "w") as f:
    f.write(output)

print(f"Plan saved to weekly_plan.md")
print("\n" + "="*60)
print(plan_text)
