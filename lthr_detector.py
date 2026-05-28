"""
Auto-detect LTHR (Lactate Threshold Heart Rate) changes from running data.
Analyzes recent hard efforts to estimate current threshold HR.
"""

import json
from datetime import date, timedelta

def estimate_lthr_from_efforts(workouts, lthr_current=173, max_hr=196, min_duration_min=15):
    """
    Estimate LTHR from recent running power data.
    
    Strategy:
    1. Find hard running efforts in last 8 weeks (tempo, threshold pace)
    2. Look for sustained efforts 15+ minutes at high HR
    3. LTHR is typically the HR at which lactate starts accumulating
    4. Use highest sustained avg HR from long efforts
    """
    
    # Filter running workouts with HR data from last 60 days
    cutoff = date.today() - timedelta(days=60)
    run_workouts = [
        w for w in workouts 
        if w.get("sport") == "running"
        and w.get("avg_hr", 0) > 0
        and (w.get("duration_min", 0) or 0) >= min_duration_min
        and date.fromisoformat(w.get("date", "2000-01-01")) >= cutoff
    ]
    
    if not run_workouts:
        return None, 0  # No running data, can't estimate
    
    # Calculate intensity from each workout
    efforts = []
    for w in run_workouts:
        avg_hr = w.get("avg_hr", 0)
        max_hr_workout = w.get("max_hr", 0)
        duration_min = w.get("duration_min", 0) or 1
        
        # Estimate intensity: workouts at 85-95% max HR are threshold efforts
        hr_intensity = avg_hr / max_hr
        
        # Only consider efforts at hard intensity (>80% max HR)
        if hr_intensity < 0.80:
            continue
        
        efforts.append({
            "date": w.get("date"),
            "avg_hr": avg_hr,
            "max_hr": max_hr_workout,
            "duration_min": duration_min,
            "hr_intensity": hr_intensity
        })
    
    if not efforts:
        return None, 0  # No threshold efforts found
    
    # Find the effort with highest sustained avg HR
    # This is most likely to be near LTHR
    best_effort = max(efforts, key=lambda e: e["avg_hr"])
    
    # Confidence based on duration: longer efforts at high HR = more confident
    confidence = min(1.0, best_effort["duration_min"] / 30)  # Full confidence at 30+ min
    
    # LTHR estimate: typically 85-90% of max HR for trained runners
    # If someone sustained 180 bpm for 30min, LTHR is likely ~180 bpm
    new_lthr_candidate = best_effort["avg_hr"]
    
    # Only recommend change if:
    # 1. Confident enough (duration and intensity)
    # 2. Change is meaningful (>2 bpm)
    # 3. New LTHR is reasonable (85-92% max HR)
    lthr_change = new_lthr_candidate - lthr_current
    hr_pct = new_lthr_candidate / max_hr
    
    if confidence < 0.4 or abs(lthr_change) < 2 or hr_pct < 0.82 or hr_pct > 0.93:
        return None, confidence  # Not confident enough to change
    
    # Cap change at 3 bpm per 8 weeks (conservative)
    if lthr_change > 0:
        new_lthr = lthr_current + min(lthr_change, 3)
    else:
        new_lthr = lthr_current + max(lthr_change, -2)  # More conservative on decreases
    
    return {
        "new_lthr": int(round(new_lthr)),
        "old_lthr": lthr_current,
        "change": int(round(new_lthr - lthr_current)),
        "best_effort_hr": int(best_effort["avg_hr"]),
        "best_effort_duration": int(best_effort["duration_min"]),
        "best_effort_date": best_effort["date"],
        "confidence": int(round(confidence * 100)),
        "hr_pct_max": int(round(hr_pct * 100))
    }, confidence

def update_zones_with_new_lthr(zones, new_lthr, max_hr, rest_hr):
    """
    Recalculate HR zones based on new LTHR.
    Uses standard percentages of LTHR.
    """
    
    # Standard zone definitions as % of LTHR
    zone_defs = {
        "z1": {"name": "Recovery",  "pct_min": 0,   "pct_max": 85},
        "z2": {"name": "Aerobic",   "pct_min": 85,  "pct_max": 95},
        "z3": {"name": "Tempo",     "pct_min": 95,  "pct_max": 100},
        "z4": {"name": "Threshold", "pct_min": 100, "pct_max": 105},
        "z5": {"name": "VO2max",    "pct_min": 105, "pct_max": 120},
    }
    
    new_zones = {}
    for zkey, zdef in zone_defs.items():
        # Calculate HR range from LTHR percentages
        hr_min = int(round((zdef["pct_min"] / 100) * new_lthr))
        hr_max = int(round((zdef["pct_max"] / 100) * new_lthr))
        
        # Ensure within physiological bounds
        hr_min = max(rest_hr, hr_min)
        hr_max = min(max_hr, hr_max)
        
        new_zones[zkey] = {
            "name": zdef["name"],
            "hr_min": hr_min,
            "hr_max": hr_max,
            "pace_slow": zones[zkey].get("pace_slow", "7:30"),  # Keep pace hints
            "pace_fast": zones[zkey].get("pace_fast", "7:00"),
        }
    
    return new_zones

if __name__ == "__main__":
    # Test
    with open("workouts.json") as f:
        test_workouts = json.load(f)
    
    result, conf = estimate_lthr_from_efforts(test_workouts)
    if result:
        print(f"LTHR estimate: {result['old_lthr']} → {result['new_lthr']} bpm (change: +{result['change']} bpm)")
        print(f"Confidence: {result['confidence']}% | {result['hr_pct_max']}% of max HR")
        print(f"Based on: {result['best_effort_duration']}min @ {result['best_effort_hr']} bpm on {result['best_effort_date']}")
    else:
        print(f"No LTHR change (confidence: {conf*100:.0f}%)")
