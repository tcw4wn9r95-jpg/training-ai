import os
import json
import anthropic
from datetime import date, timedelta
from garminconnect.workout import RunningWorkout, CyclingWorkout, WorkoutSegment, create_warmup_step, create_interval_step, create_recovery_step, create_cooldown_step
from garminconnect import Garmin
from ftp_detector import estimate_ftp_from_efforts, update_profile_with_new_ftp
from lthr_detector import estimate_lthr_from_efforts, update_zones_with_new_lthr
from garminconnect.workout import (
    RunningWorkout,
    CyclingWorkout,
    WorkoutSegment,
    create_warmup_step,
    create_interval_step,
    create_recovery_step,
    create_cooldown_step,
    create_repeat_group,
)

# ── Load profile and availability ─────────────────────────────────────────────
with open("profile.json") as f:
    profile = json.load(f)

with open("availability.json") as f:
    availability = json.load(f)

availability_notes = availability.get("notes", "")
days_data = availability.get("days", {})

if days_data:
    available_days  = [d for d, v in days_data.items() if v.get("available")]
    hours_per_day   = {d: v.get("hours", 1.0) for d, v in days_data.items() if v.get("available")}
else:
    available_days  = []
    hours_per_day   = {}

# If no days set (availability not configured yet), use sensible defaults
if not available_days:
    print("WARNING: No availability set — using default schedule.")
    print("Set your availability on the dashboard before Sunday to get a personalised plan.")
    available_days = ["Monday", "Wednesday", "Thursday", "Saturday", "Sunday"]
    hours_per_day  = {"Monday": 1.0, "Wednesday": 1.0, "Thursday": 1.5, "Saturday": 2.0, "Sunday": 1.5}

print(f"Available days: {available_days}")
print(f"Hours per day: {hours_per_day}")

# ── Garmin login ──────────────────────────────────────────────────────────────
print("Connecting to Garmin Connect...")
client = Garmin(os.environ["GARMIN_EMAIL"], os.environ["GARMIN_PASSWORD"])
client.login()
print("Logged in.")

# ── Fetch last 6 weeks of activities ─────────────────────────────────────────
end_date   = date.today()
start_date = end_date - timedelta(days=42)
activities = client.get_activities_by_date(start_date.isoformat(), end_date.isoformat())
print(f"Found {len(activities)} activities.")

FTP     = profile["cycling"]["ftp_watts"]
LTHR    = profile["cycling"]["threshold_hr"]
REST_HR = profile["running"]["resting_hr"]
MAX_HR  = profile["running"]["max_hr"]

def hr_tss(duration_min, avg_hr):
    if not avg_hr or avg_hr < 60 or not duration_min:
        return 0
    hrr  = (avg_hr - REST_HR) / (MAX_HR - REST_HR)
    lthr = (LTHR    - REST_HR) / (MAX_HR - REST_HR)
    IF   = hrr / lthr
    return round((duration_min / 60) * IF * IF * 100, 1)

workouts = []
for a in activities:
    sport_raw = a.get("activityType", {}).get("typeKey", "unknown")
    sport_map = {
        "running": "running", "cycling": "cycling",
        "road_biking": "cycling", "indoor_cycling": "cycling_indoor",
        "strength_training": "strength", "fitness_equipment": "strength",
    }
    sport        = sport_map.get(sport_raw, sport_raw)
    duration_min = round(a.get("duration", 0) / 60, 1)
    distance_km  = round(a.get("distance", 0) / 1000, 2)
    avg_hr       = a.get("averageHR", 0)
    avg_power    = a.get("avgPower", 0)
    avg_pace     = round(duration_min / distance_km, 2) if sport == "running" and distance_km > 0 else None
    tss = hr_tss(duration_min, avg_hr)

    workouts.append({
        "date": a.get("startTimeLocal", "")[:10],
        "sport": sport, "duration_min": duration_min,
        "distance_km": distance_km, "avg_hr": avg_hr,
        "max_hr": a.get("maxHR", 0), "avg_pace_min_km": avg_pace,
        "avg_power_watts": avg_power, "calories": a.get("calories", 0),
        "tss": tss,
    })

with open("workouts.json", "w") as f:
    json.dump(workouts, f, indent=2)
print("Workout history saved.")

# ── Auto-detect FTP from recent power data ────────────────────────────────────
print("\n--- Checking FTP (Cycling) ---")
ftp_result, ftp_confidence = estimate_ftp_from_efforts(workouts, ftp_current=FTP)
ftp_changed = False
if ftp_result:
    print(f"FTP increase detected: {ftp_result['old_ftp']}W → {ftp_result['new_ftp']}W")
    print(f"Confidence: {ftp_result['confidence']}% | Based on {ftp_result['best_effort_duration']}min @ {ftp_result['best_effort_power']}W")
    profile = update_profile_with_new_ftp(profile, ftp_result['new_ftp'])
    FTP = profile["cycling"]["ftp_watts"]
    ftp_changed = True
else:
    print(f"No FTP change needed (confidence too low or insufficient data)")

# ── Auto-detect LTHR from recent running data ────────────────────────────────
print("\n--- Checking LTHR (Running) ---")
lthr_result, lthr_confidence = estimate_lthr_from_efforts(workouts, lthr_current=LTHR, max_hr=MAX_HR, min_duration_min=15)
lthr_changed = False
if lthr_result:
    print(f"LTHR increase detected: {lthr_result['old_lthr']} → {lthr_result['new_lthr']} bpm")
    print(f"Confidence: {lthr_result['confidence']}% | {lthr_result['hr_pct_max']}% of max HR")
    print(f"Based on: {lthr_result['best_effort_duration']}min @ {lthr_result['best_effort_hr']} bpm on {lthr_result['best_effort_date']}")
    new_running_zones = update_zones_with_new_lthr(
        profile["running"]["zones"],
        lthr_result['new_lthr'],
        profile["running"]["max_hr"],
        profile["running"]["resting_hr"]
    )
    profile["running"]["threshold_hr"] = lthr_result['new_lthr']
    profile["running"]["zones"] = new_running_zones
    LTHR = lthr_result['new_lthr']
    lthr_changed = True
else:
    print(f"No LTHR change needed (confidence too low or insufficient data)")

# Save profile if either changed
if ftp_changed or lthr_changed:
    with open("profile.json", "w") as f:
        json.dump(profile, f, indent=2)
    print(f"\n✓ Profile updated and saved.")
    if ftp_changed and lthr_changed:
        print(f"  • FTP: {ftp_result['old_ftp']}W → {ftp_result['new_ftp']}W")
        print(f"  • LTHR: {lthr_result['old_lthr']} → {lthr_result['new_lthr']} bpm")
    elif ftp_changed:
        print(f"  • FTP: {ftp_result['old_ftp']}W → {ftp_result['new_ftp']}W")
    else:
        print(f"  • LTHR: {lthr_result['old_lthr']} → {lthr_result['new_lthr']} bpm")

# ── Build next week date map ──────────────────────────────────────────────────
today            = date.today()
days_until_mon   = (7 - today.weekday()) % 7 or 7
next_monday      = today + timedelta(days=days_until_mon)
DAY_NAMES        = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
week_dates       = {name: (next_monday + timedelta(days=i)).isoformat() for i, name in enumerate(DAY_NAMES)}

week_schedule = "\n".join(
    f"  {name} {week_dates[name]}: "
    + ("✅ AVAILABLE — " + str(hours_per_day.get(name, 1.0)) + "h max" if name in available_days else "❌ REST DAY")
    for name in DAY_NAMES
)

# ── Call Claude — ask for BOTH markdown plan AND structured JSON ──────────────
print("Calling Claude for training plan...")
claude  = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

prompt = f"""You are Diego's personal trainer. Build a detailed weekly training plan.

## ATHLETE PROFILE
- Name: Diego | Device: Garmin Fenix
- Resting HR: {REST_HR} bpm | Max HR: {MAX_HR} bpm | Threshold HR: {LTHR} bpm
- FTP (cycling): {FTP}W

## RUNNING ZONES
- Z1 Recovery:  < 145 bpm  | pace > 7:00/km
- Z2 Aerobic:   146–162 bpm | pace 6:15–6:45/km
- Z3 Tempo:     163–172 bpm | pace 5:30–6:00/km
- Z4 Threshold: 173–181 bpm | pace 4:45–5:20/km
- Z5 VO2max:    > 181 bpm   | pace < 4:30/km

## CYCLING ZONES (indoor = power, outdoor = HR only)
- Z1: < 145 bpm | < 106W  (< 55% FTP)
- Z2: 146–162 bpm | 106–141W (56–75% FTP)
- Z3: 163–172 bpm | 142–168W (76–90% FTP)
- Z4: 173–181 bpm | 169–195W (91–105% FTP)
- Z5: > 181 bpm   | 196–239W (106–120% FTP)

## STRENGTH EQUIPMENT
TRX, resistance bands, dumbbells: 6kg, 11kg, 16kg, 22kg

## NEXT WEEK AVAILABILITY
{week_schedule}
Respect available hours strictly. Longer availability = longer or harder session.
{f"Notes: {availability_notes}" if availability_notes else ""}

## LAST 6 WEEKS OF TRAINING DATA
{json.dumps(workouts, indent=2)}

## OUTPUT FORMAT — YOU MUST RETURN EXACTLY THIS STRUCTURE

Return your response in two clearly separated sections:

### SECTION 1: MARKDOWN PLAN
A detailed human-readable plan for each training day exactly as before,
with warmup/main set/cooldown, HR zones, pace or power targets, RPE, Garmin alerts, coaching notes.

### SECTION 2: JSON PLAN
After the markdown, output a JSON block wrapped in ```json ... ``` containing ONLY training days (skip rest days).
Each session must follow this exact schema:

```json
[
  {{
    "day": "Monday",
    "date": "{week_dates['Monday']}",
    "sport": "running",
    "name": "Easy aerobic run",
    "total_duration_secs": 2700,
    "steps": [
      {{
        "type": "warmup",
        "duration_secs": 600,
        "target_type": "heart_rate",
        "target_low": 130,
        "target_high": 145
      }},
      {{
        "type": "interval",
        "duration_secs": 1500,
        "target_type": "heart_rate",
        "target_low": 146,
        "target_high": 162
      }},
      {{
        "type": "cooldown",
        "duration_secs": 600,
        "target_type": "heart_rate",
        "target_low": 100,
        "target_high": 130
      }}
    ]
  }},
  {{
    "day": "Wednesday",
    "date": "{week_dates['Wednesday']}",
    "sport": "cycling_indoor",
    "name": "Threshold intervals",
    "total_duration_secs": 4500,
    "steps": [
      {{
        "type": "warmup",
        "duration_secs": 900,
        "target_type": "power",
        "target_low": 88,
        "target_high": 106
      }},
      {{
        "type": "repeat",
        "repeat_count": 4,
        "steps": [
          {{
            "type": "interval",
            "duration_secs": 480,
            "target_type": "power",
            "target_low": 169,
            "target_high": 195
          }},
          {{
            "type": "recovery",
            "duration_secs": 240,
            "target_type": "power",
            "target_low": 88,
            "target_high": 106
          }}
        ]
      }},
      {{
        "type": "cooldown",
        "duration_secs": 600,
        "target_type": "power",
        "target_low": 53,
        "target_high": 88
      }}
    ]
  }}
]
```

Sport values: "running", "cycling_indoor", "cycling_outdoor", "strength"
Target types: "heart_rate" (use bpm), "power" (use watts, indoor cycling only), "pace" (use seconds per km)
Step types: "warmup", "interval", "recovery", "cooldown", "repeat"
Strength sessions: use a single interval step with target_type "heart_rate" and duration only — no power/pace.
Only include days in available_days. Do not include rest days in the JSON.
"""

message = claude.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=6000,
    messages=[{"role": "user", "content": prompt}]
)

response = message.content[0].text
print("Plan received from Claude.")

# ── Split markdown and JSON ───────────────────────────────────────────────────
plan_md   = response
plan_json = []

if "```json" in response:
    parts     = response.split("```json")
    plan_md   = parts[0].strip()
    json_part = parts[1].split("```")[0].strip()
    try:
        plan_json = json.loads(json_part)
        print(f"Parsed {len(plan_json)} sessions from Claude's JSON.")
    except json.JSONDecodeError as e:
        print(f"WARNING: Could not parse JSON plan: {e}")
        plan_json = []

# Save both
with open("weekly_plan.md", "w") as f:
    f.write(f"# Training Plan — Week of {next_monday.strftime('%d %B %Y')}\n\n")
    f.write(f"**Generated:** {date.today().strftime('%d %B %Y')}  \n")
    f.write(f"**Available days:** {', '.join(available_days)}  \n\n---\n\n")
    f.write(plan_md)

with open("weekly_plan.json", "w") as f:
    json.dump(plan_json, f, indent=2)

print("Plans saved.")

# ── Push workouts to Garmin Connect ──────────────────────────────────────────
if not plan_json:
    print(f"\nNo sessions to upload. Check weekly_plan.json.")
else:
    print(f"\nPushing {len(plan_json)} workouts to Garmin Connect...")
    uploaded = 0

    for session in plan_json:
        sport        = session.get("sport", "running")
        name         = session.get("name", "Training session")
        session_date = session.get("date", "")
        total_secs   = session.get("total_duration_secs", 3600)
        steps_data   = session.get("steps", [])

        try:
            # Build steps with correct signatures
            steps = []
            for i, step in enumerate(steps_data):
                step_type = step.get("type", "interval")
                duration  = float(step.get("duration_secs", 600))
                order     = i + 1

                if step_type == "warmup":
                    steps.append(create_warmup_step(duration, order))
                elif step_type == "cooldown":
                    steps.append(create_cooldown_step(duration, order))
                elif step_type == "recovery":
                    steps.append(create_recovery_step(duration, order))
                else:
                    steps.append(create_interval_step(duration, order))

            if not steps:
                steps = [create_interval_step(float(total_secs), 1)]

            segment = WorkoutSegment(
                segmentOrder=1,
                sportType={"sportTypeId": 1, "sportTypeKey": "running"} if sport == "running"
                          else {"sportTypeId": 2, "sportTypeKey": "cycling"},
                workoutSteps=steps
            )

            if sport == "running":
                workout = RunningWorkout(
                    workoutName=name,
                    estimatedDurationInSecs=total_secs,
                    workoutSegments=[segment]
                )
                result = client.upload_running_workout(workout)

            elif sport in ("cycling_indoor", "cycling_outdoor", "cycling"):
                workout = CyclingWorkout(
                    workoutName=name,
                    estimatedDurationInSecs=total_secs,
                    workoutSegments=[segment]
                )
                result = client.upload_cycling_workout(workout)

            else:
                print(f"  Skipping {name} ({sport}) — unsupported type.")
                continue

            workout_id = result.get("workoutId") if isinstance(result, dict) else None
            if workout_id and session_date:
                client.schedule_workout(workout_id, session_date)
                print(f"  ✓ {name} ({sport}) → {len(steps)} steps, scheduled {session_date}")
                uploaded += 1
            elif workout_id:
                print(f"  ✓ {name} ({sport}) → {len(steps)} steps, uploaded")
                uploaded += 1
            else:
                print(f"  ⚠️  {name}: unclear response: {result}")

        except Exception as e:
            print(f"  ❌ {name}: {str(e)[:120]}")

    print(f"\nGarmin: {uploaded}/{len(plan_json)} workouts pushed.")
    if uploaded > 0:
        print("Sync your Fenix to see workouts on your watch.")

print("\n" + "="*60)
print(plan_md[:1000] + "..." if len(plan_md) > 1000 else plan_md)
