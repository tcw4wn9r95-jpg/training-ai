"""
Coach Claudio — weekly training sync
Fetches Garmin data, auto-detects FTP/LTHR, asks Claude for a periodised plan,
and pushes properly structured workouts (with real interval repeats and
correct pace/power/HR targets) back to Garmin Connect.
"""
import os
import json
from datetime import date, timedelta

import anthropic
from garminconnect import Garmin
from ftp_detector import estimate_ftp_from_efforts, update_profile_with_new_ftp
from lthr_detector import estimate_lthr_from_efforts, update_zones_with_new_lthr

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# ── Load profile & availability ───────────────────────────────────────────────
with open("profile.json") as f:
    profile = json.load(f)
with open("availability.json") as f:
    availability = json.load(f)

last_plan_md = ""
if os.path.exists("weekly_plan.md"):
    with open("weekly_plan.md") as f:
        last_plan_md = f.read()

# Load multi-week plan history so the plan builds on itself over time
plan_history = []
if os.path.exists("plan_history.json"):
    try:
        with open("plan_history.json") as f:
            plan_history = json.load(f)
    except Exception:
        plan_history = []

# Load subjective check-ins (pain, fatigue, how sessions felt) logged via the
# Coach chat. These are first-class inputs — an elite coach plans around how the
# athlete is actually responding, not just the numbers.
checkins = []
if os.path.exists("checkins.json"):
    try:
        with open("checkins.json") as f:
            checkins = json.load(f)
        if not isinstance(checkins, list):
            checkins = []
    except Exception:
        checkins = []

# Only surface check-ins from the last ~21 days (older niggles are usually resolved)
from datetime import datetime as _dt
_recent_checkins = []
_cutoff_iso = (date.today() - timedelta(days=21)).isoformat()
for c in checkins[-15:]:
    if str(c.get("date", "")) >= _cutoff_iso:
        _recent_checkins.append(c)

if _recent_checkins:
    _ci_lines = []
    for c in _recent_checkins:
        _area = f" [{c.get('affects_area')}]" if c.get("affects_area") else ""
        _ci_lines.append(f"  {c.get('date','?')} ({c.get('severity','info')}){_area}: {c.get('note','')}")
    checkins_block = (
        "The athlete logged these subjective check-ins recently. TREAT THESE AS HIGH PRIORITY — "
        "if there is pain or an affected area, do NOT load it (avoid aggravating movements, "
        "offer cross-training alternatives, keep intensity off it until resolved). If fatigue/illness/"
        "poor sleep was reported, bias toward recovery. Address these explicitly in your coaching notes:\n"
        + "\n".join(_ci_lines)
    )
else:
    checkins_block = "  (no recent subjective check-ins — plan from the objective data)"


# Build a compact multi-week summary for the prompt
if plan_history:
    history_lines = []
    for h in plan_history[-6:]:
        history_lines.append(
            f"  Week of {h.get('week_of','?')} [{h.get('phase','?')}]: "
            f"planned {h.get('planned_tss',0)} TSS, actual 7d {h.get('last_7d_actual_tss','?')} TSS, "
            f"FTP {h.get('ftp','?')}W, LTHR {h.get('lthr','?')}"
        )
    history_summary = "\n".join(history_lines)
else:
    history_summary = "  (no history yet — this is week 1)"

# Load athlete goals (set during onboarding) so plans are tailored from week 1
goals = {}
if os.path.exists("goals.json"):
    try:
        with open("goals.json") as f:
            goals = json.load(f)
    except Exception:
        goals = {}

# Body weight is single-sourced in the NutriPrep nutrition app — read Diego's
# weight log so the training plan is weight-aware (power-to-weight, fuelling).
# NutriPrep now lives in its own repo, so read over the shared cross-repo
# channel (raw.githubusercontent) and fall back to the local copy while the
# nutrition/ folder still exists in this repo (dual-run period).
weight_block = ""
def _load_diego_weightlog():
    import urllib.request
    url = ("https://raw.githubusercontent.com/tcw4wn9r95-jpg/"
           "nutriprep/main/users/diego/weight_log.json")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.load(r)
    except Exception:
        pass
    _local = os.path.join("nutrition", "users", "diego", "weight_log.json")
    if os.path.exists(_local):
        try:
            with open(_local) as f:
                return json.load(f)
        except Exception:
            pass
    return None

_wlog_raw = _load_diego_weightlog()
if _wlog_raw:
    try:
        _wlog = sorted(_wlog_raw, key=lambda x: x.get("date", ""))
        if _wlog:
            _latest = _wlog[-1]
            _recent = _wlog[-4:]
            if len(_recent) >= 2:
                _delta = _recent[-1]["weight_kg"] - _recent[0]["weight_kg"]
                weight_block = (
                    f"Current body weight {_latest['weight_kg']} kg "
                    f"(trend {_delta:+.1f} kg over last {len(_recent)} weigh-ins, from NutriPrep). "
                    "Factor weight trend into power-to-weight and recovery."
                )
            else:
                weight_block = f"Current body weight {_latest['weight_kg']} kg (from NutriPrep)."
    except Exception:
        weight_block = ""

if goals.get("primary_goal"):
    _gd = goals
    # Compute weeks-to-event if a target date is set, for taper logic
    weeks_to_event = None
    if _gd.get("target_date"):
        try:
            ev = date.fromisoformat(_gd["target_date"][:10])
            weeks_to_event = max(0, (ev - date.today()).days // 7)
        except Exception:
            weeks_to_event = None
    goals_block = (
        f"PRIMARY GOAL: {_gd.get('primary_goal','')} (type: {_gd.get('goal_type','general')})\n"
        f"TARGET EVENT: {_gd.get('target_event') or 'none'}"
        + (f" on {_gd.get('target_date')} (~{weeks_to_event} weeks away)" if weeks_to_event is not None else "") + "\n"
        f"SPORT PRIORITY: {_gd.get('sport_priority','balanced')}\n"
        f"INJURIES/LIMITS: {_gd.get('injuries','none')}\n"
        f"CURRENT VOLUME: {_gd.get('current_volume','unknown')}\n"
        f"NOTES: {_gd.get('coach_notes','')}"
    )
    # Taper guidance if an event is near
    taper_note = ""
    if weeks_to_event is not None:
        if weeks_to_event <= 1:
            taper_note = "RACE WEEK: sharp taper — cut volume ~50-60%, keep a little intensity, prioritise freshness so Form (TSB) goes positive."
        elif weeks_to_event <= 3:
            taper_note = f"~{weeks_to_event} weeks to the event: begin easing volume while holding sharpness; build toward a positive TSB on race day."
        else:
            taper_note = f"~{weeks_to_event} weeks out: still in build — develop the specific fitness the goal needs."
else:
    goals_block = "No explicit goals set yet — train balanced general fitness across running, cycling and strength until the athlete sets goals."
    taper_note = ""

availability_notes = availability.get("notes", "")
days_data = availability.get("days", {})
if days_data:
    available_days = [d for d, v in days_data.items() if v.get("available")]
    hours_per_day = {d: v.get("hours", 1.0) for d, v in days_data.items() if v.get("available")}
else:
    available_days, hours_per_day = [], {}

if not available_days:
    print("WARNING: No availability set — using default schedule.")
    available_days = ["Monday", "Wednesday", "Thursday", "Saturday", "Sunday"]
    hours_per_day = {"Monday": 1.0, "Wednesday": 1.0, "Thursday": 1.5, "Saturday": 2.0, "Sunday": 1.5}

print(f"Available days: {available_days}")
print(f"Hours per day: {hours_per_day}")

FTP = profile["cycling"]["ftp_watts"]
LTHR = profile["running"]["threshold_hr"]
REST_HR = profile["running"]["resting_hr"]
MAX_HR = profile["running"]["max_hr"]

# ── TSS helpers ───────────────────────────────────────────────────────────────
def hr_tss(duration_min, avg_hr):
    if not avg_hr or avg_hr < 60 or not duration_min:
        return 0
    hrr = (avg_hr - REST_HR) / (MAX_HR - REST_HR)
    lthr_frac = (LTHR - REST_HR) / (MAX_HR - REST_HR)
    intensity = hrr / lthr_frac if lthr_frac else 0
    return round((duration_min / 60) * intensity * intensity * 100, 1)

def power_tss(duration_min, avg_power):
    """Approximate power-based TSS using avg power as a proxy for NP."""
    if not avg_power or avg_power < 20 or not duration_min or not FTP:
        return 0
    intensity = avg_power / FTP
    return round((duration_min / 60) * intensity * intensity * 100, 1)

# ── Garmin login ──────────────────────────────────────────────────────────────
print("Connecting to Garmin Connect...")
client = Garmin(os.environ["GARMIN_EMAIL"], os.environ["GARMIN_PASSWORD"])
client.login()
print("Logged in.")

# ── Fetch last 6 weeks of activities ─────────────────────────────────────────
end_date = date.today()
start_date = end_date - timedelta(days=42)
activities = client.get_activities_by_date(start_date.isoformat(), end_date.isoformat())
print(f"Found {len(activities)} activities.")

SPORT_MAP = {
    "running": "running", "trail_running": "running", "treadmill_running": "running",
    "cycling": "cycling", "road_biking": "cycling", "mountain_biking": "cycling",
    "indoor_cycling": "cycling_indoor", "virtual_ride": "cycling_indoor",
    "strength_training": "strength", "fitness_equipment": "strength",
    "swimming": "swimming", "lap_swimming": "swimming", "open_water_swimming": "swimming",
    "yoga": "yoga", "pilates": "yoga",
    "hiking": "hiking",
    "walking": "walking",
    "rowing": "rowing",
    "elliptical": "elliptical",
    "tennis": "tennis", "squash": "tennis", "badminton": "tennis", "racquet_sports": "tennis",
    "skiing": "skiing", "alpine_skiing": "skiing", "snowboarding": "skiing",
    "soccer": "soccer", "football_soccer": "soccer",
    "boxing_or_mma": "boxing",
}

workouts = []
for a in activities:
    sport_raw = a.get("activityType", {}).get("typeKey", "unknown")
    sport = SPORT_MAP.get(sport_raw, sport_raw)
    duration_min = round(a.get("duration", 0) / 60, 1)
    distance_km = round(a.get("distance", 0) / 1000, 2)
    avg_hr = a.get("averageHR", 0)
    avg_power = a.get("avgPower", 0) or 0
    avg_pace = round(duration_min / distance_km, 2) if sport == "running" and distance_km > 0 else None

    if avg_power > 20 and "cycl" in sport:
        tss = power_tss(duration_min, avg_power)
    else:
        tss = hr_tss(duration_min, avg_hr)

    workouts.append({
        "date": a.get("startTimeLocal", "")[:10],
        "sport": sport, "duration_min": duration_min, "distance_km": distance_km,
        "avg_hr": avg_hr, "max_hr": a.get("maxHR", 0), "avg_pace_min_km": avg_pace,
        "avg_power_watts": avg_power, "calories": a.get("calories", 0), "tss": tss,
    })

with open("workouts.json", "w") as f:
    json.dump(workouts, f, indent=2)
print("Workout history saved.")

# ── Fetch sleep data ──────────────────────────────────────────────────────────
sleep_data = []
for offset in range(14):
    d = (date.today() - timedelta(days=offset)).isoformat()
    try:
        raw = client.get_sleep_data(d)
        dto = (raw or {}).get("dailySleepDTO", {})
        score_obj = (dto.get("sleepScores") or {}).get("overall", {})
        score = score_obj.get("value") if isinstance(score_obj, dict) else score_obj
        total_secs = dto.get("sleepTimeSeconds", 0) or 0
        if score or total_secs:
            sleep_data.append({
                "date": d,
                "score": int(score) if score else None,
                "duration_h": round(total_secs / 3600, 2),
                "deep_h": round((dto.get("deepSleepSeconds", 0) or 0) / 3600, 2),
                "light_h": round((dto.get("lightSleepSeconds", 0) or 0) / 3600, 2),
                "rem_h": round((dto.get("remSleepSeconds", 0) or 0) / 3600, 2),
                "awake_h": round((dto.get("awakeSleepSeconds", 0) or 0) / 3600, 2),
            })
    except Exception as e:
        print(f"Sleep data not available for {d}: {e}")
sleep_data.sort(key=lambda x: x["date"])
with open("sleep.json", "w") as f:
    json.dump(sleep_data, f, indent=2)
print(f"Sleep data saved ({len(sleep_data)} days).")

# ── Auto-detect FTP & LTHR ────────────────────────────────────────────────────
print("\n--- Checking FTP (Cycling) ---")
ftp_result, _ = estimate_ftp_from_efforts(workouts, ftp_current=FTP)
ftp_changed = False
if ftp_result:
    print(f"FTP: {ftp_result['old_ftp']}W -> {ftp_result['new_ftp']}W (confidence {ftp_result['confidence']}%)")
    profile = update_profile_with_new_ftp(profile, ftp_result['new_ftp'])
    FTP = profile["cycling"]["ftp_watts"]
    ftp_changed = True
else:
    print("No FTP change.")

print("\n--- Checking LTHR (Running) ---")
lthr_result, _ = estimate_lthr_from_efforts(workouts, lthr_current=LTHR, max_hr=MAX_HR, min_duration_min=15)
lthr_changed = False
if lthr_result:
    print(f"LTHR: {lthr_result['old_lthr']} -> {lthr_result['new_lthr']} bpm (confidence {lthr_result['confidence']}%)")
    profile["running"]["zones"] = update_zones_with_new_lthr(
        profile["running"]["zones"], lthr_result['new_lthr'],
        profile["running"]["max_hr"], profile["running"]["resting_hr"])
    profile["running"]["threshold_hr"] = lthr_result['new_lthr']
    LTHR = lthr_result['new_lthr']
    lthr_changed = True
else:
    print("No LTHR change.")

if ftp_changed or lthr_changed:
    with open("profile.json", "w") as f:
        json.dump(profile, f, indent=2)
    print("Profile updated.")

# Activities-only mode: fetch Garmin data + update profile, then stop.
# Used by the sync_activities workflow so the dashboard can refresh workouts
# without triggering a full plan regeneration.
if os.environ.get("ACTIVITIES_ONLY", "").strip().lower() in ("1", "true"):
    print("ACTIVITIES_ONLY=true — skipping plan generation.")
    raise SystemExit(0)

# ── Build next-week date map ──────────────────────────────────────────────────
today = date.today()
days_until_mon = (7 - today.weekday()) % 7 or 7
next_monday = today + timedelta(days=days_until_mon)
week_dates = {name: (next_monday + timedelta(days=i)).isoformat() for i, name in enumerate(DAY_NAMES)}

# Determine where we are in the 4-week periodisation block.
# Week index is based on real elapsed time since the journey started (the Monday
# of the first-ever generated plan). Generating multiple plans in one week does
# NOT advance the index — only the passage of time does.
_block_phases = ["base", "build", "peak", "recovery"]

journey_start_file = "journey_start.json"
# Reset journey on forced regeneration so block numbering restarts from week 1.
# Also reset if stored start is in the future relative to next_monday (data anomaly).
_force_journey = os.environ.get("FORCE_GENERATE", "").strip().lower() in ("1", "true")
if os.path.exists(journey_start_file):
    with open(journey_start_file) as _f:
        _stored_start = date.fromisoformat(json.load(_f)["started"])
    if _force_journey or _stored_start > next_monday:
        os.remove(journey_start_file)
        print(f"Journey reset — starting from week 1 (force={_force_journey}, stored={_stored_start}, next_monday={next_monday})")

if not os.path.exists(journey_start_file):
    # First-ever plan (or after reset): record next_monday as the journey start.
    journey_start = next_monday
    with open(journey_start_file, "w") as _f:
        json.dump({"started": journey_start.isoformat()}, _f)
    print(f"Journey start recorded: {journey_start}")
else:
    with open(journey_start_file) as _f:
        journey_start = date.fromisoformat(json.load(_f)["started"])

current_week_index = max(0, (today - journey_start).days // 7)
current_phase = _block_phases[current_week_index % 4]
next_phase = _block_phases[(current_week_index + 1) % 4]

# ── Skip if a plan already exists for this week ───────────────────────────────
# A plan, once generated, is never automatically regenerated mid-block.
# Coach edits (committed directly to weekly_plan.json) take priority and are
# preserved. A new plan is only generated when none exists for next_monday.
# FORCE_GENERATE=1 is a developer escape hatch only — never set by the app.
_force = os.environ.get("FORCE_GENERATE", "").strip().lower() in ("1", "true")
if not _force:
    existing_status = {}
    if os.path.exists("plan_status.json"):
        try:
            with open("plan_status.json") as f:
                existing_status = json.load(f)
        except Exception:
            pass
    existing_week = existing_status.get("week_of")
    if existing_week == next_monday.isoformat():
        print(f"Plan already exists for week of {next_monday} (status: {existing_status.get('status','?')}).")
        print("Skipping — coach edits are preserved. Set FORCE_GENERATE=1 to override (dev only).")
        raise SystemExit(0)  # Exit 0 = success, workflow marks as green

week_schedule = "\n".join(
    f"  {name} {week_dates[name]}: "
    + (f"AVAILABLE — up to {hours_per_day.get(name, 1.0)}h" if name in available_days else "REST DAY")
    for name in DAY_NAMES
)

recent_4wk = [w for w in workouts if (today - date.fromisoformat(w["date"])).days <= 28] if workouts else []
last_4wk_tss = round(sum(w["tss"] for w in recent_4wk))
last_wk_tss = round(sum(w["tss"] for w in workouts if (today - date.fromisoformat(w["date"])).days <= 7)) if workouts else 0

# Sleep context for the plan prompt
_sleep_now = []
if os.path.exists("sleep.json"):
    try:
        with open("sleep.json") as _sf:
            _sleep_now = json.load(_sf)
    except Exception:
        pass
if _sleep_now:
    _recent_sleep = [d for d in _sleep_now if d.get("score")][-7:]
    _avg_score = round(sum(d["score"] for d in _recent_sleep) / max(1, len(_recent_sleep))) if _recent_sleep else None
    _poor_nights = [d["date"] for d in _recent_sleep if d["score"] < 65]
    _last_night = _sleep_now[-1] if _sleep_now else None
    sleep_block = (
        f"7-day avg sleep score: {_avg_score}/100. "
        + (f"Last night: {_last_night['score']}/100, {_last_night['duration_h']}h total, {_last_night['deep_h']}h deep. " if _last_night else "")
        + (f"Poor nights (<65): {', '.join(_poor_nights)}." if _poor_nights else "Sleep quality looks consistent.")
    )
else:
    sleep_block = "No sleep data available yet."

# ── Build the prompt ──────────────────────────────────────────────────────────
print("Calling Claude for training plan...")
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

prompt = f"""You are Coach Claudio, Diego's endurance coach — the calibre who works with high-performing athletes. You write structured, periodised plans grounded in exercise physiology: progressive overload, polarised 80/20 intensity distribution, specificity to the goal, periodisation toward peak adaptation, supercompensation, and respect for recovery. Every session has a clear physiological purpose and explicit targets. You plan around how the athlete is actually responding — both the data AND their subjective feedback — never a generic template.

## ATHLETE
Name: Diego | Device: Garmin Fenix
Resting HR {REST_HR} | Max HR {MAX_HR} | Running threshold HR {LTHR} bpm | FTP {FTP}W
{weight_block}

## GOALS & TARGETS (the athlete set these — tailor every plan toward them)
{goals_block}
{taper_note}

## SUBJECTIVE CHECK-INS (pain / fatigue / how training felt) — WEIGH HEAVILY
{checkins_block}

## RUNNING ZONES (pace is primary, HR is reference)
Z1 Recovery: >7:00/km, <145 bpm
Z2 Aerobic: 6:15-6:45/km, 146-162 bpm
Z3 Tempo: 5:30-6:00/km, 163-172 bpm
Z4 Threshold: 4:45-5:20/km, 173-181 bpm
Z5 VO2max: <4:30/km, >181 bpm

## CYCLING ZONES (indoor=power, outdoor=HR)
Z1 <106W / <145 bpm | Z2 106-141W / 146-162 bpm | Z3 142-168W / 163-172 bpm
Z4 169-195W / 173-181 bpm | Z5 196-239W / >181 bpm

## STRENGTH EQUIPMENT
TRX, resistance bands, dumbbells 6/11/16/22 kg

## RECENT LOAD
Last 7 days: ~{last_wk_tss} TSS | Last 28 days: ~{last_4wk_tss} TSS

## SLEEP & RECOVERY (from Garmin — factor this into session intensity and weekly structure)
{sleep_block}

## MULTI-WEEK HISTORY (this is week {current_week_index + 1} of the athlete's journey)
You have planned the following weeks already. The plan must CONTINUE this arc — never restart from scratch:
{history_summary}

## LAST WEEK'S PLAN (continue and progress it, do NOT copy it)
{last_plan_md[:1500] if last_plan_md else "No previous plan — this is week 1, start with a controlled base week."}

## PERIODIZATION — YOU ARE IN THE *{current_phase.upper()}* PHASE THIS WEEK
- This week's phase is **{current_phase}** (next week will be {next_phase}). Honour the 4-week arc: base -> build -> peak -> recovery.
- base: build aerobic volume, mostly easy. build: add threshold/sweet-spot, raise TSS. peak: sharpen with VO2max/race-pace, highest intensity. recovery: cut volume ~40%, easy only, let adaptation land.
- Progress from last week's ACTUAL load (not just planned). If the athlete completed last week -> raise weekly TSS 5-10% (except recovery weeks, which drop). If sessions were missed -> hold or slightly reduce.
- Carry forward the training thread: if last week introduced threshold work, this week should develop it (e.g. longer intervals or more reps), not switch to something unrelated.
- Rotate the *specific* key session so it's fresh, but keep the progression logical.
- 1-2 hard days max, separated by easy/rest. Most volume easy (80/20).
- Reflect FTP {FTP}W and LTHR {LTHR} — if these rose recently, the athlete is fitter; nudge targets accordingly.
- ALWAYS bias the plan toward the athlete's PRIMARY GOAL above. If there's a target event, make the key sessions specific to it (e.g. a 10K goal needs threshold + race-pace running; a gran fondo needs long endurance rides). If the event is near, follow the taper guidance. This is week {current_week_index + 1}; if it's week 1, use the athlete's stated current volume as the starting load — do NOT start generic or random.


## NEXT WEEK AVAILABILITY
{week_schedule}
Respect available hours strictly. {f"Athlete note: {availability_notes}" if availability_notes else ""}

## TRAINING DATA (last 6 weeks)
{json.dumps(workouts, indent=2)}

## OUTPUT — TWO SECTIONS

### SECTION 1: MARKDOWN PLAN
For each training day write a clear block:
### <Day> — <Session name>
**Sport:** <running / cycling indoor / cycling outdoor / strength>
**Duration:** <min> | **Planned TSS:** <number> | **Focus:** <one line purpose>
#### Warm-up
- target + description
#### Main set
- the work, with reps/targets
#### Cool-down
- target
**Coach notes:** one or two sentences on execution/feel.

End with:
## Week Summary
- Total planned TSS, the week's focus (base/build/peak/recovery), and one coaching sentence.

### SECTION 2: JSON PLAN
Then a ```json block with ONLY training days. Follow this schema EXACTLY.

TARGET RULES (critical — match these precisely):
- running: every step target_type="pace", target_low/target_high in SECONDS PER KM where target_low is the SLOWER bound and target_high is the FASTER bound (e.g. easy 405/375, threshold 320/285). Put the HR zone in the step "description".
- cycling_indoor: target_type="power", target_low/target_high in WATTS.
- cycling_outdoor: target_type="heart_rate", target_low/target_high in BPM.
- strength: no targets; put exercises in step "description" and a full list in top-level "notes".
- Use "repeat" blocks for intervals (e.g. 4x8min). Never flatten intervals.

```json
[
  {{
    "day": "Monday",
    "date": "{week_dates['Monday']}",
    "sport": "running",
    "name": "Easy aerobic run",
    "total_duration_secs": 2700,
    "planned_tss": 35,
    "focus": "Aerobic base, conversational",
    "steps": [
      {{"type": "warmup", "duration_secs": 600, "target_type": "pace", "target_low": 450, "target_high": 405, "description": "Z1 easy, <145 bpm"}},
      {{"type": "interval", "duration_secs": 1500, "target_type": "pace", "target_low": 405, "target_high": 375, "description": "Z2 aerobic 146-162 bpm"}},
      {{"type": "cooldown", "duration_secs": 600, "target_type": "pace", "target_low": 480, "target_high": 420, "description": "Z1 easy"}}
    ]
  }},
  {{
    "day": "Wednesday",
    "date": "{week_dates['Wednesday']}",
    "sport": "cycling_indoor",
    "name": "Threshold 4x8",
    "total_duration_secs": 4200,
    "planned_tss": 75,
    "focus": "Raise FTP with threshold repeats",
    "steps": [
      {{"type": "warmup", "duration_secs": 900, "target_type": "power", "target_low": 88, "target_high": 120, "description": "Spin up, build to Z2"}},
      {{"type": "repeat", "repeat_count": 4, "steps": [
        {{"type": "interval", "duration_secs": 480, "target_type": "power", "target_low": 169, "target_high": 185, "description": "Z4 threshold, smooth 90+ rpm"}},
        {{"type": "recovery", "duration_secs": 240, "target_type": "power", "target_low": 88, "target_high": 110, "description": "Easy spin"}}
      ]}},
      {{"type": "cooldown", "duration_secs": 420, "target_type": "power", "target_low": 70, "target_high": 100, "description": "Easy spin down"}}
    ]
  }},
  {{
    "day": "Friday",
    "date": "{week_dates['Friday']}",
    "sport": "strength",
    "name": "Lower body & core",
    "total_duration_secs": 2700,
    "planned_tss": 30,
    "focus": "Strength endurance for legs and core",
    "notes": "3 rounds: 12x goblet squat 22kg, 10x RDL 22kg, 15x TRX split squat/leg, 20x band glute bridge, 45s plank. 60s rest between rounds.",
    "steps": [
      {{"type": "warmup", "duration_secs": 300, "description": "Leg swings, hip circles, bodyweight squats"}},
      {{"type": "interval", "duration_secs": 1980, "description": "3 rounds of the main circuit"}},
      {{"type": "cooldown", "duration_secs": 420, "description": "Stretch hips, hamstrings, glutes"}}
    ]
  }}
]
```

Only include available days. Use realistic pace seconds-per-km values for Diego.

### SECTION 3: 4-WEEK BLOCK OUTLINE
After the JSON, add a SECOND ```json block (labelled exactly ```json-block) giving a LIGHTWEIGHT outline of the full 4-week training block this week belongs to. This is for the athlete to see the bigger picture — NOT full step detail. Week 1 is the current week ({next_monday.isoformat()}). Project weeks 2-4 following the periodisation arc (current phase: {current_phase}). For each week give the phase, target weekly TSS, and a one-line summary plus session headlines (day, sport, name, focus, planned_tss) — no steps.

```json-block
[
  {{"week_index": {current_week_index + 1}, "week_of": "{next_monday.isoformat()}", "phase": "{current_phase}", "target_tss": 0, "summary": "one line", "sessions": [
    {{"day": "Monday", "sport": "running", "name": "Easy run", "focus": "aerobic base", "planned_tss": 35}}
  ]}}
]
```
Project all 4 weeks with sensible progression (build weeks raise TSS, recovery week drops ~40%).
"""

message = claude.messages.create(
    model="claude-sonnet-4-6",  # Sonnet for plan generation — deeper reasoning on periodisation, check-ins, injuries. ~+$0.25/mo vs Haiku.
    max_tokens=8000,
    messages=[{"role": "user", "content": prompt}],
)
response = message.content[0].text
print("Plan received from Claude.")

# ── Split markdown & JSON ─────────────────────────────────────────────────────
plan_md = response
plan_json = []
plan_block = []

# Parse the 4-week block outline first (labelled ```json-block) and remove it
if "```json-block" in response:
    try:
        block_part = response.split("```json-block")[1].split("```")[0].strip()
        plan_block = json.loads(block_part)
        # Enforce week_of dates — the LLM sometimes drifts from the prompt's week_dates
        for i, wk in enumerate(plan_block):
            wk["week_of"] = (next_monday + timedelta(days=7 * i)).isoformat()
        print(f"Parsed {len(plan_block)} week(s) in block outline.")
    except (json.JSONDecodeError, IndexError) as e:
        print(f"WARNING: block outline parse failed: {e}")
    # Strip the block section out so the detailed-plan parser doesn't trip on it
    response_main = response.split("```json-block")[0]
else:
    response_main = response

# Parse the detailed weekly plan
parse_error = None
if "```json" in response_main:
    parts = response_main.split("```json")
    plan_md = parts[0].strip()
    json_part = parts[1].split("```")[0].strip()
    try:
        plan_json = json.loads(json_part)
        # Enforce session dates from week_dates — the LLM sometimes invents its own dates
        for session in plan_json:
            day_label = session.get("day", "")
            if day_label in week_dates:
                session["date"] = week_dates[day_label]
        print(f"Parsed {len(plan_json)} sessions.")
    except json.JSONDecodeError as e:
        parse_error = str(e)
        print(f"WARNING: JSON parse failed: {e}")

# Fail loudly if we didn't get a usable plan — better than committing an empty one
if not plan_json:
    print("=" * 70)
    print("ERROR: Plan generation produced 0 sessions.")
    print("Parse error: " + (parse_error or "no ```json block found in response"))
    print("=" * 70)
    print("RAW CLAUDE RESPONSE (first 4000 chars):")
    print(response[:4000])
    print("=" * 70)
    print("Likely causes:")
    print("  (a) availability.json has no days selected → Claude has nothing to plan")
    print("  (b) Claude returned malformed JSON")
    print("  (c) prompt or template issue")
    raise SystemExit("Plan generation failed — see error above")

with open("weekly_plan.md", "w") as f:
    f.write(f"# Training Plan — Week of {next_monday.strftime('%d %B %Y')}\n\n")
    f.write(f"**Generated:** {date.today().strftime('%d %B %Y')}  \n")
    f.write(f"**Available days:** {', '.join(available_days)}  \n\n---\n\n")
    f.write(plan_md)
with open("weekly_plan.json", "w") as f:
    json.dump(plan_json, f, indent=2)

# Merge the detailed current-week sessions into week 1 of the block,
# so the app shows full step detail for the current week and outlines for 2-4.
if plan_block:
    for wk in plan_block:
        if wk.get("week_of") == next_monday.isoformat() and plan_json:
            wk["sessions"] = plan_json  # full detail for the current week
            wk["detailed"] = True
    with open("plan_block.json", "w") as f:
        json.dump(plan_block, f, indent=2)
    print(f"Saved plan_block.json ({len(plan_block)} weeks).")
else:
    # Fallback: at least store the current week so navigation has data
    fallback_block = [{
        "week_index": current_week_index + 1,
        "week_of": next_monday.isoformat(),
        "phase": current_phase,
        "target_tss": sum(s.get("planned_tss", 0) for s in plan_json),
        "summary": "Current week",
        "sessions": plan_json,
        "detailed": True,
    }]
    with open("plan_block.json", "w") as f:
        json.dump(fallback_block, f, indent=2)
    print("Saved plan_block.json (current week only — outline parse failed).")
print("Plans saved.")

# ── Mark plan as DRAFT (awaiting review) — do NOT push to Garmin here ─────────
# The push happens on demand when Diego taps "Let's do this!" in the app,
# after he's reviewed and optionally adjusted the plan via Coach Claudio.
plan_status = {
    "status": "draft",
    "generated": date.today().isoformat(),
    "week_of": next_monday.isoformat(),
    "sessions": len(plan_json),
    "pushed": False,
}
with open("plan_status.json", "w") as f:
    json.dump(plan_status, f, indent=2)
print("Plan marked as DRAFT — review it in the app, then tap 'Let's do this!' to push.")

# ── Archive to plan history so weeks build on each other ─────────────────────
# plan_history was already loaded at the top; append this week's snapshot.
snapshot = {
    "week_of": next_monday.isoformat(),
    "generated": date.today().isoformat(),
    "phase": current_phase,
    "planned_tss": sum(s.get("planned_tss", 0) for s in plan_json),
    "last_7d_actual_tss": last_wk_tss,
    "last_28d_actual_tss": last_4wk_tss,
    "ftp": FTP,
    "lthr": LTHR,
    "sessions": [
        {"day": s.get("day"), "sport": s.get("sport"), "name": s.get("name"),
         "planned_tss": s.get("planned_tss"), "focus": s.get("focus")}
        for s in plan_json
    ],
}
plan_history.append(snapshot)
plan_history = plan_history[-12:]  # keep last 12 weeks
with open("plan_history.json", "w") as f:
    json.dump(plan_history, f, indent=2)
print(f"Archived to plan history ({len(plan_history)} weeks tracked, phase: {current_phase}).")

print("\n" + "=" * 60)
print(plan_md[:800] + ("..." if len(plan_md) > 800 else ""))
