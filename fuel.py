"""
Coach Claudio — training fuel for COMPLETED sessions, shared with NutriPrep.

Coach Claudio owns the fuel number: how much extra food a day's *completed*
training needs. The dashboard computes it live (fuelFor in dashboard.html);
this module is the same maths in Python so sync.py can publish it as
`fuel.json` after every Garmin sync, for the NutriPrep household app to show.
Keep the two in step — tests/test_fuel.py runs the dashboard's own JavaScript
against this module to catch drift.

Rules (see NUTRITION.md → Training-day fuelling):
  * Only completed sessions add fuel. A planned session adds nothing until it
    has been done and synced.
  * Session energy = the watch's calories net of resting (1 kcal/kg/h), or,
    without a watch figure, (MET − 1) × kg × hours from the Compendium.
  * ~60% of it as carbohydrate (total ≤ 10 g/kg), protein +0.12 g/kg (+0.2 on
    strength-only days, ≤ 30 g, total ≤ 2.0 g/kg), fat takes the rest (≤ 15 g),
    water +600 ml per hour.

NutriPrep owns the plan: the baseline macros AND the body weight come from
its users/diego/macro_targets.json (nutritionist plan + Diego's goals);
Claudio's own nutrition_plan.json, then reference values, only fill gaps.
"""
from __future__ import annotations

import json
import math
import urllib.request

NUTRIPREP_RAW = "https://raw.githubusercontent.com/tcw4wn9r95-jpg/nutriprep/main"
NUTRIPREP_MEMBER = "diego"
NUTRIPREP_KEYS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")

MET_TABLE = {
    "run": {"easy": 8.3, "mod": 9.8, "hard": 11.8},
    "bike": {"easy": 6.8, "mod": 8.5, "hard": 10.8},
    "strength": {"easy": 3.5, "mod": 5.0, "hard": 6.0},
    "swim": {"easy": 5.8, "mod": 8.3, "hard": 10.0},
    "row": {"easy": 4.8, "mod": 7.0, "hard": 8.5},
    "walk": {"easy": 3.0, "mod": 3.5, "hard": 4.3},
    "hike": {"easy": 5.3, "mod": 6.0, "hard": 7.0},
    "yoga": {"easy": 2.5, "mod": 3.0, "hard": 4.0},
    "elliptical": {"easy": 4.6, "mod": 5.0, "hard": 7.0},
    "other": {"easy": 4.5, "mod": 6.0, "hard": 8.0},
}


def jround(x: float) -> int:
    """JavaScript Math.round (halves round up), not Python's banker's rounding."""
    return int(math.floor(x + 0.5))


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) and not math.isnan(x) else None


def sport_of(w: dict) -> str:
    s = w.get("sport") or ""
    if s == "running":
        return "run"
    if "cycl" in s:
        return "bike"
    return {"strength": "strength", "swimming": "swim", "yoga": "yoga", "hiking": "hike",
            "walking": "walk", "rowing": "row", "elliptical": "elliptical", "tennis": "tennis",
            "skiing": "ski", "soccer": "soccer", "boxing": "boxing"}.get(s, "other")


def session_hours(s: dict) -> float:
    if _num(s.get("total_duration_secs")):
        return s["total_duration_secs"] / 3600
    if _num(s.get("duration_min")):
        return s["duration_min"] / 60
    if sport_of(s) == "strength":
        return 0.75
    t = _num(s.get("planned_tss")) or _num(s.get("tss"))
    if t:
        return min(3, max(0.5, t / 50))
    return 1


def intensity_of(s: dict, hours: float, lthr) -> str:
    t = _num(s.get("planned_tss")) or _num(s.get("tss")) or 0
    per = t / hours if hours > 0 else 0
    if sport_of(s) == "strength" and not _num(s.get("avg_hr")):
        return "mod"
    if _num(s.get("avg_hr")) and lthr:
        r = s["avg_hr"] / lthr
        if r >= 0.98:
            return "hard"
        if r >= 0.90:
            return "mod"
        if r > 0:
            return "easy"
    if not per:
        return "mod"
    return "easy" if per < 50 else "mod" if per < 78 else "hard"


def session_kcal(s: dict, kg: float, lthr) -> dict:
    """Net (above-resting) energy of a completed session."""
    hours = session_hours(s)
    if _num(s.get("calories")) and s["calories"] > 0:
        return {"kcal": max(0, jround(s["calories"] - kg * hours)), "hours": hours, "src": "measured"}
    met = MET_TABLE.get(sport_of(s), MET_TABLE["other"])
    v = met.get(intensity_of(s, hours, lthr)) or met["mod"]
    return {"kcal": max(0, jround((v - 1) * kg * hours)), "hours": hours, "src": "estimated"}


def reference_targets(body: dict) -> dict:
    kg = _num(body.get("weight_kg")) or 75
    height = _num(body.get("height_cm")) or 175
    age = _num(body.get("age")) or 40
    female = body.get("sex") == "female"
    activity = _num(body.get("activity")) or 1.375
    goal = body.get("goal") or "maintain"
    ree = 10 * kg + 6.25 * height - 5 * age + (-161 if female else 5)
    maint = ree * activity
    kcal = max(maint * 0.85, ree * 1.05) if goal == "loss" else maint * 1.10 if goal == "gain" else maint
    protein = kg * (1.8 if goal == "loss" else 1.6)
    fat = kcal * 0.30 / 9
    carbs = (kcal - protein * 4 - fat * 9) / 4
    if carbs < kg * 3:
        need = (kg * 3 - carbs) * 4
        fat = max(kcal * 0.20 / 9, fat - need / 9)
        carbs = (kcal - protein * 4 - fat * 9) / 4
    return {"kcal": jround(kcal / 10) * 10, "protein_g": jround(protein), "carbs_g": jround(carbs),
            "fat_g": jround(fat), "fiber_g": jround(14 * kcal / 1000)}


def base_targets(nutrition_plan: dict | None, nutriprep_targets: dict | None) -> dict:
    """Baseline macros: NutriPrep > Claudio's plan > reference (same order as the app)."""
    plan = nutrition_plan or {}
    ref = reference_targets(plan.get("body") or {})
    t = plan.get("targets") or {}
    out = {}
    for k in NUTRIPREP_KEYS:
        np_v = _num((nutriprep_targets or {}).get(k))
        if np_v and np_v > 0:
            out[k] = jround(np_v)
            continue
        raw = t.get(k)
        v = _num(raw.get("value")) if isinstance(raw, dict) else _num(raw)
        out[k] = jround(v) if v and v > 0 else ref[k]
    return out


def body_kg(nutrition_plan: dict | None, nutriprep_targets: dict | None = None) -> float:
    np_kg = _num(((nutriprep_targets or {}).get("body") or {}).get("weight_kg"))
    return np_kg or _num(((nutrition_plan or {}).get("body") or {}).get("weight_kg")) or 75


def fuel_for_day(sessions: list[dict], kg: float, base: dict, lthr) -> dict | None:
    """Extra targets for one day's COMPLETED sessions, or None on a rest day."""
    if not sessions:
        return None
    use = [session_kcal(s, kg, lthr) for s in sessions]
    kcal = sum(u["kcal"] for u in use)
    hours = sum(u["hours"] for u in use)
    strength_only = all(sport_of(s) == "strength" for s in sessions)
    add_carb = jround(kcal * 0.60 / 4)
    add_carb = min(add_carb, max(0, jround(kg * 10 - base["carbs_g"])))
    add_prot = jround(min(kg * 0.2 if strength_only else kg * 0.12, 30))
    add_prot = max(0, min(add_prot, jround(kg * 2.0 - base["protein_g"])))
    rest = kcal - add_carb * 4 - add_prot * 4
    add_fat = max(0, min(15, jround(rest / 9)))
    return {
        "session_kcal": kcal,
        "hours": round(hours, 2),
        "src": "measured" if all(u["src"] == "measured" for u in use) else "estimated",
        "sessions": [(s.get("name") or s.get("sport") or "session").replace("_", " ") for s in sessions],
        "add": {"kcal": add_carb * 4 + add_prot * 4 + add_fat * 9, "carbs_g": add_carb,
                "protein_g": add_prot, "fat_g": add_fat, "water_ml": jround(hours * 600 / 50) * 50},
    }


def build_fuel(workouts: list[dict], nutrition_plan: dict | None, nutriprep_targets: dict | None,
               lthr, since: str | None = None) -> dict:
    """{"days": {iso: fuel}} for every date with completed sessions (optionally since a date)."""
    kg, base = body_kg(nutrition_plan, nutriprep_targets), base_targets(nutrition_plan, nutriprep_targets)
    by_day: dict[str, list] = {}
    for w in workouts or []:
        d = str(w.get("date") or "")[:10]
        if d and (since is None or d >= since):
            by_day.setdefault(d, []).append(w)
    days = {d: fuel_for_day(ws, kg, base, lthr) for d, ws in sorted(by_day.items())}
    return {"version": 1, "member": NUTRIPREP_MEMBER, "body_kg": kg, "base": base,
            "rule": "completed sessions only", "days": {d: f for d, f in days.items() if f}}


def load_nutriprep_targets(base: str = NUTRIPREP_RAW) -> dict | None:
    try:
        with urllib.request.urlopen(f"{base}/users/{NUTRIPREP_MEMBER}/macro_targets.json", timeout=10) as r:
            data = json.load(r)
        return data if isinstance(data, dict) else None
    except Exception:
        return None
