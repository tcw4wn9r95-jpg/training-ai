"""
NutriPrep — Sunday weekly meal plan generator.
Reads household + user profiles, calls Claude Sonnet, parses three JSON blocks
(menu / shopping / prep), post-processes with food_safety + lux_products, writes
all output files and computes the notification schedule for the week.
"""
import os, json, sys, re
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import anthropic

BASE = Path(__file__).parent
LUX = ZoneInfo("Europe/Luxembourg")
MEMBERS = ["diego", "diana"]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# ── Load shared files ─────────────────────────────────────────────────────────
with open(BASE / "household.json") as f:
    household = json.load(f)
with open(BASE / "schedule.json") as f:
    schedule = json.load(f)

nutrition_plan: dict = {}
if (BASE / "nutrition_plan.json").exists():
    with open(BASE / "nutrition_plan.json") as f:
        nutrition_plan = json.load(f)

menu_history: list = []
if (BASE / "menu_history.json").exists():
    with open(BASE / "menu_history.json") as f:
        menu_history = json.load(f)

# ── Load per-user data ────────────────────────────────────────────────────────
users: dict = {}
for member in MEMBERS:
    udir = BASE / "users" / member
    u: dict = {}
    for fname in ["goals", "macro_targets", "weight_log", "checkins"]:
        p = udir / f"{fname}.json"
        if p.exists():
            with open(p) as f:
                u[fname] = json.load(f)
        else:
            u[fname] = [] if fname in ("weight_log", "checkins") else {}
    users[member] = u

# ── Compute next Monday ───────────────────────────────────────────────────────
today = date.today()
days_until_mon = (7 - today.weekday()) % 7 or 7
next_monday = today + timedelta(days=days_until_mon)
week_dates = {name: (next_monday + timedelta(days=i)).isoformat() for i, name in enumerate(DAY_NAMES)}

# ── Skip if plan already exists (unless forced) ───────────────────────────────
_force = os.environ.get("FORCE_GENERATE", "").strip().lower() in ("1", "true")
if not _force and (BASE / "plan_status.json").exists():
    with open(BASE / "plan_status.json") as f:
        existing = json.load(f)
    if existing.get("week_of") == next_monday.isoformat() and existing.get("status") == "published":
        print(f"Plan already exists for {next_monday}. Use FORCE_GENERATE=1 to override.")
        sys.exit(0)

# ── Build member context ──────────────────────────────────────────────────────
member_blocks = []
for member in MEMBERS:
    u = users[member]
    mt = u.get("macro_targets") or {}
    goals = u.get("goals") or {}
    wlog = u.get("weight_log") or []
    recent_w = sorted(wlog, key=lambda x: x["date"])[-4:] if wlog else []

    # Weight trend summary
    if len(recent_w) >= 2:
        delta = recent_w[-1]["weight_kg"] - recent_w[0]["weight_kg"]
        trend = f"{recent_w[-1]['weight_kg']} kg (last 4 weeks: {delta:+.1f} kg)"
    elif recent_w:
        trend = f"{recent_w[-1]['weight_kg']} kg (starting)"
    else:
        trend = f"Start: {goals.get('start_weight_kg', '?')} kg (no weigh-ins yet)"

    target_w = goals.get("target_weight_kg", "?")
    rate = goals.get("target_rate_kg_per_week", 0.5)
    goal_type = goals.get("goal_type", "maintain")

    # Recent check-ins (last 14 days)
    cutoff = (today - timedelta(days=14)).isoformat()
    recent_ci = [c for c in (u.get("checkins") or []) if c.get("date", "") >= cutoff]
    ci_text = ""
    if recent_ci:
        ci_text = "\n  Recent check-ins:\n" + "\n".join(
            f"    {c['date']}: {c.get('note', '')} (mood:{c.get('mood','?')} energy:{c.get('energy','?')})"
            for c in recent_ci[-5:]
        )

    # Get macro targets from nutrition plan if available
    plan_targets = (nutrition_plan.get("per_member_targets") or {}).get(member) or {}
    if plan_targets and plan_targets.get("kcal"):
        macro_src = "nutritionist plan"
        mt = {**mt, **{k: v for k, v in plan_targets.items() if v is not None}}
    else:
        macro_src = mt.get("source", "estimate")

    member_blocks.append(f"""
### {member.capitalize()}
Goal: {goal_type.replace('_', ' ').title()} · Target: {target_w} kg at −{rate} kg/wk
Weight: {trend}
Daily targets ({macro_src}): {mt.get('kcal','?')} kcal · {mt.get('protein_g','?')}g protein · {mt.get('carbs_g','?')}g carbs · {mt.get('fat_g','?')}g fat · {mt.get('fiber_g','?')}g fibre{ci_text}""")

# ── Nutritionist guidelines ───────────────────────────────────────────────────
plan_notes = []
if nutrition_plan.get("prescribed_foods"):
    plan_notes.append("Prescribed: " + ", ".join(nutrition_plan["prescribed_foods"]))
if nutrition_plan.get("restricted_foods"):
    plan_notes.append("Restricted/avoid: " + ", ".join(nutrition_plan["restricted_foods"]))
if nutrition_plan.get("nutritionist_notes"):
    plan_notes.append("Notes: " + nutrition_plan["nutritionist_notes"])
nutrition_block = "\n".join(plan_notes) if plan_notes else "No nutritionist plan uploaded yet — use individual macro targets as authority."

# ── History (variety) ─────────────────────────────────────────────────────────
if menu_history:
    hist_lines = []
    for h in menu_history[-3:]:
        meals = h.get("meal_names", [])
        hist_lines.append(f"  Week of {h.get('week_of','?')}: {', '.join(meals[:6])}" + (" …" if len(meals) > 6 else ""))
    history_block = "\n".join(hist_lines)
else:
    history_block = "  No history yet — first week, prioritise variety and simplicity."

# ── Allergens & preferences ───────────────────────────────────────────────────
allergens = household.get("allergies", []) + household.get("intolerances", [])
dislikes = household.get("dislikes", [])
cuisines = household.get("cuisines_loved", [])
budget = household.get("budget_eur_per_week", 130)
max_prep = household.get("max_prep_minutes_sunday", 150)
max_cook = household.get("max_cook_minutes_weekday", 25)

# ── Schedule context ──────────────────────────────────────────────────────────
meal_times = schedule.get("meal_times", {})
eat_out_days = schedule.get("eat_out_days", [])
schedule_block = "\n".join(f"  {slot.replace('_', ' ').title()}: {t}" for slot, t in meal_times.items())
if eat_out_days:
    schedule_block += f"\n  Eat out: {', '.join(eat_out_days)} (still include a light home meal for those days)"

# ── Build the prompt ──────────────────────────────────────────────────────────
diego_kcal = (users["diego"].get("macro_targets") or {}).get("kcal", "?")
diana_kcal = (users["diana"].get("macro_targets") or {}).get("kcal", "?")

prompt = f"""You are Coach Léa, a registered dietitian coach for a household in Luxembourg.
Generate a complete, evidence-based weekly meal plan for the week of {next_monday.strftime('%d %B %Y')} (Monday–Sunday).

## HOUSEHOLD
Two people: Diego and Diana. They eat the SAME dishes, just different portion sizes.
Allergies (ABSOLUTE — never include): {', '.join(allergens) if allergens else 'none'}
Dislikes (avoid): {', '.join(dislikes) if dislikes else 'none'}
Preferred cuisines: {', '.join(cuisines) if cuisines else 'varied'}
Weekly food budget: €{budget} (shopping for both)
Max Sunday batch-prep time: {max_prep} min active
Max weekday cooking time: {max_cook} min

## MEMBER PROFILES
{"".join(member_blocks)}

## NUTRITIONIST GUIDELINES (clinical authority — follow above individual targets)
{nutrition_block}

## MEAL SCHEDULE (Luxembourg time)
{schedule_block}

## PAST WEEKS (avoid repeating the same dishes)
{history_block}

## YOUR RULES
1. **One menu for the household, two sets of portions.** Each meal has a `portions.diego` and `portions.diana` with their own ingredient quantities and macros. The dish is the same; only amounts differ.
2. **All 5 slots every day**: breakfast, am_snack, lunch, pm_snack, dinner — no exceptions.
3. **Snacks must be genuinely healthy**: whole foods (fruit, veg, nuts, yogurt, hummus), never ultra-processed.
4. **Maximise Sunday batch-prep**: set `prep_ahead: true` for anything that can be cooked Sunday. Keep `cook_minutes_day_of` ≤ {max_cook} for all main meals (assembly/reheating only on weekdays).
5. **Luxembourg ingredients only**: all items must be available in Luxembourg supermarkets (Cactus, Auchan, Delhaize, Aldi, Lidl). Provide French name in parentheses on first mention.
6. **Evidence-based**: align with EFSA Dietary Reference Values and WHO guidelines. Sustainable weight loss ≈ 0.25–0.75 kg/week; no crash diets, detoxes, or unproven supplements.
7. **Hit each member's daily macro targets** (±10% tolerance). Use `day_totals` to verify.
8. Each week: include oily fish at least twice; legumes on at least 3 days; ≥ 5 portions of veg per day per person.
9. Batch cooking should produce enough portions for 3–4 days before needing fresh cooking.
10. Assign each prep batch a `food_category` from: poultry, red_meat, fish_seafood, eggs_cooked, rice, grains_pasta, legumes, vegetables_cooked, vegetables_raw_prepped, soup_stew, sauce_dairy, dairy, baked_goods, generic.

## WEEK DATES
Monday: {week_dates['Monday']} | Tuesday: {week_dates['Tuesday']} | Wednesday: {week_dates['Wednesday']}
Thursday: {week_dates['Thursday']} | Friday: {week_dates['Friday']}
Saturday: {week_dates['Saturday']} | Sunday: {week_dates['Sunday']}

## OUTPUT — FOUR SECTIONS IN ORDER

### SECTION 1: MARKDOWN MENU
Write a clean, readable summary for each day (day name, each slot with emoji + meal name + key ingredients + macros for each person). End with a weekly totals table.

### SECTION 2: MENU JSON
Output a ```json-menu block. Schema (FOLLOW EXACTLY):

```json-menu
[
  {{
    "day": "Monday",
    "date": "{week_dates['Monday']}",
    "meals": [
      {{
        "slot": "breakfast",
        "name": "Meal name",
        "time": "07:30",
        "prep_ahead": true,
        "cook_minutes_day_of": 3,
        "recipe": ["Step 1", "Step 2", "Step 3"],
        "storage_ref": "prep_batch_1",
        "food_category": "dairy",
        "portions": {{
          "diego": {{
            "ingredients": [{{"item": "Greek yogurt", "qty": "200 g"}}, {{"item": "Mixed berries", "qty": "100 g"}}],
            "macros": {{"kcal": 380, "protein_g": 28, "carbs_g": 40, "fat_g": 12, "fiber_g": 4}}
          }},
          "diana": {{
            "ingredients": [{{"item": "Greek yogurt", "qty": "150 g"}}, {{"item": "Mixed berries", "qty": "80 g"}}],
            "macros": {{"kcal": 300, "protein_g": 22, "carbs_g": 32, "fat_g": 9, "fiber_g": 3}}
          }}
        }}
      }}
    ],
    "day_totals": {{
      "diego": {{"kcal": {diego_kcal}, "protein_g": 0, "carbs_g": 0, "fat_g": 0}},
      "diana": {{"kcal": {diana_kcal}, "protein_g": 0, "carbs_g": 0, "fat_g": 0}}
    }}
  }}
]
```

### SECTION 3: SHOPPING JSON
Output a ```json-shopping block. Pre-aggregate ALL ingredients for BOTH members across ALL 7 days. Each item = total household quantity needed for the week. Include French name.

```json-shopping
[
  {{"name_en": "Chicken breast", "name_fr": "Blanc de poulet", "qty": "2.0 kg", "food_category": "poultry"}}
]
```

### SECTION 4: PREP JSON
Output a ```json-prep block. List Sunday batch steps in logical cooking order (grains first, then proteins, then veg). Include `day_of_assembly` showing what to do each day with the batch.

```json-prep
[
  {{
    "id": "prep_batch_1",
    "title": "Batch title",
    "order": 1,
    "active_minutes": 20,
    "steps": ["Step 1", "Step 2"],
    "yields": ["What is produced — quantity"],
    "food_category": "poultry",
    "day_of_assembly": {{
      "Monday": "Reheat 150g chicken, add salad",
      "Tuesday": "Slice cold chicken into wrap"
    }}
  }}
]
```

Generate all 7 days. Be specific and realistic. Verify that each person's `day_totals` sum to within ±10% of their kcal target.
"""

print("Calling Claude for meal plan...")
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=14000,
    messages=[{"role": "user", "content": prompt}],
)
response = message.content[0].text
print("Plan received from Claude.")

# ── Parse the three JSON blocks ───────────────────────────────────────────────
def extract_block(text: str, label: str) -> str | None:
    """Extract content from a ```{label} … ``` block."""
    pattern = rf"```{re.escape(label)}\s*(.*?)```"
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else None


plan_md = response
menu_json: list = []
shopping_json: list = []
prep_json: list = []
errors = []

for label, target, name in [
    ("json-menu", "menu_json", "menu"),
    ("json-shopping", "shopping_json", "shopping"),
    ("json-prep", "prep_json", "prep"),
]:
    raw_block = extract_block(response, label)
    if raw_block:
        try:
            parsed = json.loads(raw_block)
            if label == "json-menu":
                menu_json = parsed
            elif label == "json-shopping":
                shopping_json = parsed
            else:
                prep_json = parsed
            print(f"Parsed {name}: {len(parsed)} items.")
        except json.JSONDecodeError as e:
            errors.append(f"JSON parse error in {label}: {e}")
    else:
        errors.append(f"Missing ```{label} block in response.")

# Extract markdown (everything before the first json-menu block)
if "```json-menu" in response:
    plan_md = response.split("```json-menu")[0].strip()

if not menu_json:
    print("=" * 70)
    print("ERROR: No menu generated.")
    for e in errors:
        print("  " + e)
    print("RESPONSE (first 3000 chars):")
    print(response[:3000])
    sys.exit("Plan generation failed.")

# Enforce correct dates (LLM sometimes drifts)
for day_data in menu_json:
    day_label = day_data.get("day", "")
    if day_label in week_dates:
        day_data["date"] = week_dates[day_label]

# ── Allergen safety check ─────────────────────────────────────────────────────
allergen_list = [a.lower() for a in allergens]
for item in shopping_json:
    name_en_lower = item.get("name_en", "").lower()
    for allergen in allergen_list:
        if allergen in name_en_lower:
            sys.exit(f"SAFETY VIOLATION: allergen '{allergen}' found in shopping list item '{item['name_en']}'! Aborting.")

print("Allergen check passed.")

# ── Post-process shopping list ────────────────────────────────────────────────
from lux_products import enrich_item

for item in shopping_json:
    enrich_item(item)

shopping_sorted = sorted(shopping_json, key=lambda x: x.get("aisle", "zzz"))

total_est_eur = round(budget * 0.85)  # rough estimate (85% of budget)

shopping_out = {
    "week_of": next_monday.isoformat(),
    "currency": "EUR",
    "est_total_eur": total_est_eur,
    "items": shopping_sorted,
}

# ── Post-process prep plan (food safety) ─────────────────────────────────────
from food_safety import validate_prep_plan

prep_json = validate_prep_plan(prep_json)
prep_total_min = sum(b.get("active_minutes", 0) for b in prep_json)

prep_out = {
    "week_of": next_monday.isoformat(),
    "prep_day": schedule.get("prep_day", "Sunday"),
    "prep_start_time": schedule.get("prep_start_time", "15:00"),
    "total_active_minutes": prep_total_min,
    "batches": prep_json,
}

# ── Compute notification schedule ─────────────────────────────────────────────
def to_lux_dt(day_date: date, time_str: str) -> str:
    h, m = map(int, time_str.split(":"))
    return datetime(day_date.year, day_date.month, day_date.day, h, m, tzinfo=LUX).isoformat()


events: list[dict] = []
for day_data in menu_json:
    day_date = date.fromisoformat(day_data["date"])
    day_name = day_data["day"]

    # Sunday: weigh-in + prep reminders
    if day_name == "Sunday":
        events.append({
            "id": f"weighin-{day_date.isoformat()}",
            "type": "weigh_in",
            "audience": MEMBERS,
            "at": to_lux_dt(day_date, "08:00"),
            "title": "Sunday weigh-in ⚖️",
            "body": "Log your weight to track your progress this week.",
            "sent": False,
        })
        prep_start = schedule.get("prep_start_time", "15:00")
        events.append({
            "id": f"prep-{day_date.isoformat()}",
            "type": "prep",
            "audience": MEMBERS,
            "at": to_lux_dt(day_date, prep_start),
            "title": "Meal prep time 🥗",
            "body": f"~{prep_total_min // 60}h{prep_total_min % 60:02d} of prep sets up your whole week. Tap for the steps.",
            "sent": False,
        })

    for meal in day_data.get("meals", []):
        slot = meal["slot"]
        meal_time = meal.get("time") or meal_times.get(slot)
        if not meal_time:
            continue

        if slot in ("am_snack", "pm_snack"):
            emoji = "🍎" if slot == "am_snack" else "🥜"
            events.append({
                "id": f"snack-{day_date.isoformat()}-{slot}",
                "type": "snack",
                "audience": MEMBERS,
                "at": to_lux_dt(day_date, meal_time),
                "title": f"Snack time {emoji}",
                "body": f"{meal['name']} — keeps you on track toward your goal.",
                "sent": False,
            })
        elif slot in ("lunch", "dinner") and meal.get("cook_minutes_day_of", 0) > 0:
            cook_min = meal["cook_minutes_day_of"]
            meal_dt = datetime.fromisoformat(to_lux_dt(day_date, meal_time))
            reminder_dt = meal_dt - timedelta(minutes=cook_min + 5)
            events.append({
                "id": f"cook-{day_date.isoformat()}-{slot}",
                "type": "cook",
                "audience": MEMBERS,
                "at": reminder_dt.isoformat(),
                "title": f"Start {'dinner' if slot == 'dinner' else 'lunch'} soon 🍳",
                "body": f"{meal['name']} — {cook_min} min. Tap for recipe.",
                "sent": False,
            })

# Sort events chronologically
events.sort(key=lambda e: e["at"])
notif_out = {"tz": "Europe/Luxembourg", "events": events}

# ── Write all output files ────────────────────────────────────────────────────
with open(BASE / "weekly_menu.md", "w") as f:
    f.write(f"# Meal Plan — Week of {next_monday.strftime('%d %B %Y')}\n\n")
    f.write(f"**Generated:** {today.strftime('%d %B %Y')}  \n")
    f.write(f"**Diego:** {users['diego'].get('macro_targets', {}).get('kcal','?')} kcal/day  \n")
    f.write(f"**Diana:** {users['diana'].get('macro_targets', {}).get('kcal','?')} kcal/day  \n\n---\n\n")
    f.write(plan_md)

with open(BASE / "weekly_menu.json", "w") as f:
    json.dump(menu_json, f, indent=2)

with open(BASE / "shopping_list.json", "w") as f:
    json.dump(shopping_out, f, indent=2)

with open(BASE / "prep_plan.json", "w") as f:
    json.dump(prep_out, f, indent=2)

with open(BASE / "notif_schedule.json", "w") as f:
    json.dump(notif_out, f, indent=2)

# ── Update plan status ────────────────────────────────────────────────────────
plan_status = {
    "status": "published",
    "generated": today.isoformat(),
    "week_of": next_monday.isoformat(),
    "meal_count": sum(len(d.get("meals", [])) for d in menu_json),
    "shopping_items": len(shopping_sorted),
    "prep_batches": len(prep_json),
    "prep_minutes": prep_total_min,
    "notification_events": len(events),
}
with open(BASE / "plan_status.json", "w") as f:
    json.dump(plan_status, f, indent=2)

# ── Archive to menu history ───────────────────────────────────────────────────
all_meal_names = []
for day_data in menu_json:
    for meal in day_data.get("meals", []):
        if meal.get("slot") not in ("am_snack", "pm_snack"):
            all_meal_names.append(meal.get("name", ""))

snapshot = {
    "week_of": next_monday.isoformat(),
    "generated": today.isoformat(),
    "meal_names": all_meal_names[:10],
    "shopping_items": len(shopping_sorted),
    "prep_minutes": prep_total_min,
    "day_kcal": {
        m: round(sum(
            d["day_totals"].get(m, {}).get("kcal", 0) for d in menu_json if d.get("day_totals")
        ) / max(1, len(menu_json)))
        for m in MEMBERS
    },
}
menu_history.append(snapshot)
menu_history = menu_history[-12:]
with open(BASE / "menu_history.json", "w") as f:
    json.dump(menu_history, f, indent=2)

print("\n" + "=" * 60)
print(f"✓ Weekly menu: {len(menu_json)} days")
print(f"✓ Shopping list: {len(shopping_sorted)} items")
print(f"✓ Prep plan: {len(prep_json)} batches, ~{prep_total_min} min active")
print(f"✓ Notifications: {len(events)} events scheduled")
print(f"✓ Plan saved for week of {next_monday}")
if errors:
    print("\nNon-fatal warnings:")
    for e in errors:
        print("  ⚠", e)
