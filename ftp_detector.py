"""
Auto-detect FTP changes from Garmin power data.
Analyzes recent hard efforts to estimate current FTP.
"""

import json
from datetime import date, timedelta
from collections import defaultdict

def estimate_ftp_from_efforts(workouts, ftp_current=177, min_power_threshold=None):
    """
    Estimate FTP from recent power data.
    
    Strategy:
    1. Find hard efforts (power > 90% current FTP) in last 8 weeks
    2. Look for sustained high-power segments (5+ min at Z4+)
    3. Calculate IF (Intensity Factor) from these efforts
    4. Estimate new FTP conservatively
    """
    
    if not min_power_threshold:
        min_power_threshold = ftp_current * 0.90  # 90% FTP = hard efforts
    
    # Filter cycling workouts with power data from last 60 days
    cutoff = date.today() - timedelta(days=60)
    power_workouts = [
        w for w in workouts 
        if (w.get("sport") == "cycling_indoor" or w.get("sport") == "cycling") 
        and w.get("avg_power_watts", 0) > 0
        and date.fromisoformat(w.get("date", "2000-01-01")) >= cutoff
    ]
    
    if not power_workouts:
        return None, 0  # No power data, can't estimate
    
    # Calculate Intensity Factor for each workout
    efforts = []
    for w in power_workouts:
        avg_power = w.get("avg_power_watts", 0)
        duration_hours = (w.get("duration_min", 0) or 1) / 60
        
        if avg_power < min_power_threshold:
            continue  # Not a hard effort
        
        # Intensity Factor = avg_power / FTP
        IF = avg_power / ftp_current
        
        # TSS = (duration_hours) * IF^2 * 100
        tss = duration_hours * IF * IF * 100
        
        efforts.append({
            "date": w.get("date"),
            "avg_power": avg_power,
            "duration_min": w.get("duration_min", 0),
            "IF": IF,
            "TSS": tss
        })
    
    if not efforts:
        return None, 0  # No hard efforts found
    
    # Find the workout with highest IF (closest to threshold)
    # This is more reliable than average, as it represents actual FTP-level effort
    best_effort = max(efforts, key=lambda e: e["IF"])
    
    # Confidence: how sustained was this effort?
    # Long efforts at high power = more confident
    confidence = min(1.0, best_effort["duration_min"] / 20)  # Full confidence at 20+ min
    
    # Conservative FTP estimate
    # If someone averaged 190W for 20min, their FTP is ~190W (0.95 * 20min power)
    # If they averaged 210W for 5min, their FTP is ~200W (0.95 * 5min power)
    new_ftp_candidate = best_effort["avg_power"] * 0.95
    
    # Only recommend change if confident AND improvement is meaningful (>5W)
    ftp_change = new_ftp_candidate - ftp_current
    
    if confidence < 0.3 or ftp_change < 5:
        return None, confidence  # Not confident enough to change
    
    # Cap increase at 10W per 8 weeks (conservative)
    new_ftp = ftp_current + min(ftp_change, 10)
    
    return {
        "new_ftp": round(new_ftp),
        "old_ftp": ftp_current,
        "change": round(new_ftp - ftp_current),
        "best_effort_power": round(best_effort["avg_power"]),
        "best_effort_duration": best_effort["duration_min"],
        "best_effort_date": best_effort["date"],
        "confidence": round(confidence * 100)
    }, confidence

def update_profile_with_new_ftp(profile, new_ftp):
    """
    Update power zones based on new FTP.
    Preserves HR zones unchanged.
    """
    old_ftp = profile["cycling"]["ftp_watts"]
    
    # Recalculate power zones (standard percentages of FTP)
    zones = {
        "z1": {"name": "Recovery",  "pct_min": 0,   "pct_max": 55},
        "z2": {"name": "Aerobic",   "pct_min": 56,  "pct_max": 75},
        "z3": {"name": "Tempo",     "pct_min": 76,  "pct_max": 90},
        "z4": {"name": "Threshold", "pct_min": 91,  "pct_max": 105},
        "z5": {"name": "VO2max",    "pct_min": 106, "pct_max": 120},
    }
    
    new_zones = {}
    for zkey, zdef in zones.items():
        pmin = (zdef["pct_min"] / 100) * new_ftp
        pmax = (zdef["pct_max"] / 100) * new_ftp
        new_zones[zkey] = {
            "name": zdef["name"],
            "hr_min": profile["cycling"]["zones"][zkey]["hr_min"],  # Keep HR unchanged
            "hr_max": profile["cycling"]["zones"][zkey]["hr_max"],
            "power_min": int(round(pmin)),
            "power_max": int(round(pmax)),
            "pct_ftp_min": zdef["pct_min"],
            "pct_ftp_max": zdef["pct_max"]
        }
    
    profile["cycling"]["ftp_watts"] = new_ftp
    profile["cycling"]["zones"] = new_zones
    
    return profile

if __name__ == "__main__":
    # Test
    with open("workouts.json") as f:
        test_workouts = json.load(f)
    
    result, conf = estimate_ftp_from_efforts(test_workouts)
    if result:
        print(f"FTP estimate: {result['old_ftp']} → {result['new_ftp']}W (change: +{result['change']}W)")
        print(f"Confidence: {result['confidence']}%")
        print(f"Based on: {result['best_effort_duration']}min @ {result['best_effort_power']}W on {result['best_effort_date']}")
    else:
        print(f"No FTP change (confidence: {conf*100:.0f}%)")
