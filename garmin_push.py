"""
garmin_push.py — shared Garmin upload logic for Coach Claudio.
Used by both the scheduled generate workflow (optional) and the on-demand
"Let's do this!" push workflow. Keeps the workout-building in one place.
"""
from garminconnect.workout import (
    RunningWorkout, CyclingWorkout, WorkoutSegment,
    create_warmup_step, create_interval_step,
    create_recovery_step, create_cooldown_step, create_repeat_group,
    TargetType,
)


# ── Target builder ────────────────────────────────────────────────────────────
def make_target(step, sport):
    """Return (target_type_dict, value_one, value_two).

    CRITICAL: Garmin expects targetValueOne/Two as SIBLINGS of targetType on the
    step, not nested inside targetType. We return them separately so build_step
    can set them as step attributes (the library's ExecutableStep allows extras).
    """
    tt = step.get("target_type", "")
    low = float(step.get("target_low", 0) or 0)
    high = float(step.get("target_high", 0) or 0)
    no_target = ({"workoutTargetTypeId": TargetType.NO_TARGET,
                  "workoutTargetTypeKey": "no.target", "displayOrder": 1}, None, None)
    if not low or not high:
        return no_target
    if tt == "pace":
        # Claude gives sec/km; low=slower, high=faster.
        # Garmin speed target in m/s: valueOne = slower (lower speed), valueTwo = faster (higher speed).
        slower_speed = round(1000.0 / low, 4)
        faster_speed = round(1000.0 / high, 4)
        return ({"workoutTargetTypeId": TargetType.SPEED, "workoutTargetTypeKey": "speed.zone",
                 "displayOrder": 1}, slower_speed, faster_speed)
    if tt == "power":
        return ({"workoutTargetTypeId": TargetType.POWER, "workoutTargetTypeKey": "power.zone",
                 "displayOrder": 1}, low, high)
    if tt == "heart_rate":
        return ({"workoutTargetTypeId": TargetType.HEART_RATE, "workoutTargetTypeKey": "heart.rate.zone",
                 "displayOrder": 1}, low, high)
    return no_target


def build_step(step, order, sport):
    stype = step.get("type", "interval")
    dur = float(step.get("duration_secs", 600))
    target_type, v1, v2 = make_target(step, sport)
    desc = step.get("description", "")[:120]
    if stype == "warmup":
        s = create_warmup_step(dur, order, target_type)
    elif stype == "cooldown":
        s = create_cooldown_step(dur, order, target_type)
    elif stype == "recovery":
        s = create_recovery_step(dur, order, target_type)
    else:
        s = create_interval_step(dur, order, target_type)
    if v1 is not None:
        s.targetValueOne = v1
    if v2 is not None:
        s.targetValueTwo = v2
    try:
        s.description = desc
    except Exception:
        pass
    return s


def build_steps(steps_data, sport):
    """Build steps including real repeat groups."""
    out = []
    order = 1
    for step in steps_data:
        if step.get("type") == "repeat":
            inner = []
            for sub in step.get("steps", []):
                inner.append(build_step(sub, order, sport))
                order += 1
            out.append(create_repeat_group(int(step.get("repeat_count", 2)), inner, order))
            order += 1
        else:
            out.append(build_step(step, order, sport))
            order += 1
    return out


def make_strength_workout_json(name, steps_data, notes):
    total = sum(s.get("duration_secs", 600) for s in steps_data) or 2700
    steps = []
    for i, step in enumerate(steps_data):
        stype = step.get("type", "interval")
        type_id = 1 if stype == "warmup" else 2 if stype == "cooldown" else 3
        type_key = "warmup" if stype == "warmup" else "cooldown" if stype == "cooldown" else "interval"
        steps.append({
            "type": "ExecutableStepDTO", "stepOrder": i + 1,
            "stepType": {"stepTypeId": type_id, "stepTypeKey": type_key},
            "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time", "displayable": True},
            "endConditionValue": float(step.get("duration_secs", 600)),
            "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"},
            "description": step.get("description", "")[:120],
        })
    return {
        "workoutName": name, "description": (notes or "")[:1000],
        "sportType": {"sportTypeId": 4, "sportTypeKey": "fitness_equipment"},
        "estimatedDurationInSecs": int(total),
        "workoutSegments": [{
            "segmentOrder": 1,
            "sportType": {"sportTypeId": 4, "sportTypeKey": "fitness_equipment"},
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
    """Upload every session in plan_json to Garmin and schedule it. Returns count uploaded."""
    if not plan_json:
        print("\nNo sessions to upload.")
        return 0
    cleanup_existing(client, plan_json)
    print(f"\nPushing {len(plan_json)} workouts to Garmin...")
    uploaded = 0
    for session in plan_json:
        sport = session.get("sport", "running")
        name = session.get("name", "Session")
        sdate = session.get("date", "")
        total_secs = session.get("total_duration_secs", 3600)
        steps_data = session.get("steps", [])
        notes = session.get("notes", "")
        try:
            if sport == "strength":
                result = client.upload_workout(make_strength_workout_json(name, steps_data, notes))
                wid = result.get("workoutId") if isinstance(result, dict) else None
                if wid and sdate:
                    client.schedule_workout(wid, sdate)
                    print(f"  OK {name} (strength) scheduled {sdate}")
                    uploaded += 1
                continue

            steps = build_steps(steps_data, sport) or [create_interval_step(float(total_secs), 1)]
            if sport == "running":
                seg = WorkoutSegment(segmentOrder=1, sportType={"sportTypeId": 1, "sportTypeKey": "running"}, workoutSteps=steps)
                wk = RunningWorkout(workoutName=name, estimatedDurationInSecs=total_secs, workoutSegments=[seg])
                result = client.upload_running_workout(wk)
            elif sport in ("cycling_indoor", "cycling_outdoor", "cycling"):
                seg = WorkoutSegment(segmentOrder=1, sportType={"sportTypeId": 2, "sportTypeKey": "cycling"}, workoutSteps=steps)
                wk = CyclingWorkout(workoutName=name, estimatedDurationInSecs=total_secs, workoutSegments=[seg])
                result = client.upload_cycling_workout(wk)
            else:
                print(f"  skip {name} ({sport})")
                continue

            wid = result.get("workoutId") if isinstance(result, dict) else None
            if wid and sdate:
                client.schedule_workout(wid, sdate)
                print(f"  OK {name} ({sport}) {len(steps)} top-steps scheduled {sdate}")
                uploaded += 1
            elif wid:
                print(f"  OK {name} ({sport}) uploaded")
                uploaded += 1
            else:
                print(f"  ?? {name}: {result}")
        except Exception as e:
            print(f"  FAIL {name}: {str(e)[:140]}")
    print(f"\nGarmin: {uploaded}/{len(plan_json)} workouts pushed.")
    return uploaded
