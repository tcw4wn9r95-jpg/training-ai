"""
garmin_push.py — shared Garmin upload logic for Coach Claudio.

Builds workouts as PLAIN DICTS and uploads via client.upload_workout(), which is
stable across garminconnect versions. This avoids the fragile model classes
(RunningWorkout/create_*_step) whose constructor signatures have changed between
releases and caused "ExecutableStep() takes no arguments" on the runner.
"""

# Garmin sport type IDs
SPORT_IDS = {
    "running": (1, "running"),
    "cycling": (2, "cycling"),
    "cycling_indoor": (2, "cycling"),
    "cycling_outdoor": (2, "cycling"),
    "strength": (4, "fitness_equipment"),
}

# Step type IDs
STEP_IDS = {
    "warmup": (1, "warmup"),
    "cooldown": (2, "cooldown"),
    "interval": (3, "interval"),
    "recovery": (4, "recovery"),
    "rest": (5, "rest"),
}

NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}


def make_target(step):
    """Return a dict of the target fields to merge into a step.

    Garmin expects targetType + targetValueOne/Two as SIBLING keys on the step.
    Running -> speed.zone (m/s), cycling indoor -> power.zone (W),
    cycling outdoor -> heart.rate.zone (bpm).
    """
    tt = step.get("target_type", "")
    low = float(step.get("target_low", 0) or 0)
    high = float(step.get("target_high", 0) or 0)
    if not low or not high:
        return {"targetType": dict(NO_TARGET)}

    if tt == "pace":
        # Claude gives sec/km; low=slower, high=faster.
        # Garmin speed target m/s: valueOne = slower (lower speed), valueTwo = faster (higher speed).
        return {
            "targetType": {"workoutTargetTypeId": 5, "workoutTargetTypeKey": "speed.zone", "displayOrder": 1},
            "targetValueOne": round(1000.0 / low, 4),
            "targetValueTwo": round(1000.0 / high, 4),
        }
    if tt == "power":
        return {
            "targetType": {"workoutTargetTypeId": 2, "workoutTargetTypeKey": "power.zone", "displayOrder": 1},
            "targetValueOne": low, "targetValueTwo": high,
        }
    if tt == "heart_rate":
        return {
            "targetType": {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone", "displayOrder": 1},
            "targetValueOne": low, "targetValueTwo": high,
        }
    return {"targetType": dict(NO_TARGET)}


def executable_step(step, order):
    """Build one ExecutableStepDTO as a plain dict."""
    stype = step.get("type", "interval")
    type_id, type_key = STEP_IDS.get(stype, STEP_IDS["interval"])
    dur = float(step.get("duration_secs", 600))
    d = {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {"stepTypeId": type_id, "stepTypeKey": type_key, "displayOrder": type_id},
        "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True},
        "endConditionValue": dur,
        "description": (step.get("description", "") or "")[:120],
    }
    d.update(make_target(step))
    return d


def build_steps(steps_data):
    """Build the workoutSteps list, including real repeat groups, as plain dicts."""
    out = []
    order = 1
    for step in steps_data:
        if step.get("type") == "repeat":
            child_steps = []
            for sub in step.get("steps", []):
                child_steps.append(executable_step(sub, order))
                order += 1
            out.append({
                "type": "RepeatGroupDTO",
                "stepOrder": order,
                "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
                "numberOfIterations": int(step.get("repeat_count", 2)),
                "smartRepeat": False,
                "endCondition": {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayable": False},
                "endConditionValue": float(step.get("repeat_count", 2)),
                "workoutSteps": child_steps,
            })
            order += 1
        else:
            out.append(executable_step(step, order))
            order += 1
    return out


def build_workout_dict(session):
    """Build a complete workout payload dict for client.upload_workout()."""
    sport = session.get("sport", "running")
    sport_id, sport_key = SPORT_IDS.get(sport, SPORT_IDS["running"])
    name = session.get("name", "Session")
    total = session.get("total_duration_secs") or sum(
        s.get("duration_secs", 600) for s in session.get("steps", [])
    ) or 3600

    if sport == "strength":
        steps = []
        for i, step in enumerate(session.get("steps", [])):
            tid, tkey = STEP_IDS.get(step.get("type", "interval"), STEP_IDS["interval"])
            steps.append({
                "type": "ExecutableStepDTO", "stepOrder": i + 1,
                "stepType": {"stepTypeId": tid, "stepTypeKey": tkey, "displayOrder": tid},
                "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True},
                "endConditionValue": float(step.get("duration_secs", 600)),
                "targetType": dict(NO_TARGET),
                "description": (step.get("description", "") or "")[:120],
            })
        desc = (session.get("notes", "") or "")[:1000]
    else:
        steps = build_steps(session.get("steps", [])) or [executable_step({"type": "interval", "duration_secs": total}, 1)]
        desc = (session.get("focus", "") or "")[:1000]

    return {
        "workoutName": name,
        "description": desc,
        "sportType": {"sportTypeId": sport_id, "sportTypeKey": sport_key, "displayOrder": sport_id},
        "estimatedDurationInSecs": int(total),
        "workoutSegments": [{
            "segmentOrder": 1,
            "sportType": {"sportTypeId": sport_id, "sportTypeKey": sport_key, "displayOrder": sport_id},
            "workoutSteps": steps,
        }],
    }


def cleanup_existing(client, plan_json):
    """Delete this week's templates + unschedule the dates so we replace, not duplicate."""
    print("\nCleaning up existing workouts for this week...")
    plan_names = {s.get("name", "").strip().lower() for s in plan_json}
    plan_dates = {s.get("date", "") for s in plan_json if s.get("date")}
    removed = 0
    try:
        existing = client.get_workouts(0, 200)
        if isinstance(existing, list):
            for w in existing:
                if w.get("workoutName", "").strip().lower() in plan_names and w.get("workoutId"):
                    try:
                        client.delete_workout(w["workoutId"]); removed += 1
                    except Exception:
                        pass
    except Exception as e:
        print(f"  template cleanup warning: {str(e)[:60]}")
    months = {(d[:4], d[5:7]) for d in plan_dates}
    for yr, mo in months:
        try:
            sched = client.get_scheduled_workouts(int(yr), int(mo))
            items = sched.get("calendarItems", []) if isinstance(sched, dict) else []
            for item in items:
                if item.get("date", "") in plan_dates:
                    try:
                        client.unschedule_workout(item["id"]); removed += 1
                    except Exception:
                        pass
        except Exception:
            pass
    print(f"  Removed {removed} existing item(s).")


def push_plan_to_garmin(client, plan_json):
    """Upload + schedule every session in plan_json. Returns count uploaded."""
    if not plan_json:
        print("\nNo sessions to upload.")
        return 0
    cleanup_existing(client, plan_json)
    print(f"\nPushing {len(plan_json)} workouts to Garmin...")
    uploaded = 0
    for session in plan_json:
        name = session.get("name", "Session")
        sdate = session.get("date", "")
        sport = session.get("sport", "running")
        try:
            payload = build_workout_dict(session)
            result = client.upload_workout(payload)
            wid = result.get("workoutId") if isinstance(result, dict) else None
            if wid and sdate:
                client.schedule_workout(wid, sdate)
                print(f"  OK {name} ({sport}) scheduled {sdate}")
                uploaded += 1
            elif wid:
                print(f"  OK {name} ({sport}) uploaded (no date)")
                uploaded += 1
            else:
                print(f"  ?? {name}: {str(result)[:100]}")
        except Exception as e:
            print(f"  FAIL {name}: {str(e)[:140]}")
    print(f"\nGarmin: {uploaded}/{len(plan_json)} workouts pushed.")
    return uploaded
