import os, json, anthropic
from datetime import date, timedelta
from garminconnect import Garmin

# Credentials come from GitHub Secrets (set up in step 4)
client = Garmin(os.environ["GARMIN_EMAIL"], os.environ["GARMIN_PASSWORD"])
client.login()

# Fetch last 30 days of activities
end = date.today()
start = end - timedelta(days=30)
activities = client.get_activities_by_date(start.isoformat(), end.isoformat())

# Simplify to just what Claude needs
workouts = []
for a in activities:
    workouts.append({
        "date": a.get("startTimeLocal", "")[:10],
        "sport": a.get("activityType", {}).get("typeKey", "unknown"),
        "duration_min": round(a.get("duration", 0) / 60, 1),
        "distance_km": round(a.get("distance", 0) / 1000, 2),
        "avg_hr": a.get("averageHR", 0),
        "calories": a.get("calories", 0),
    })

# Save data to file (gets committed to repo as your history)
with open("workouts.json", "w") as f:
    json.dump(workouts, f, indent=2)

# Call Claude for your weekly plan
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

message = claude.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1000,
    messages=[{
        "role": "user",
        "content": f"""You are my personal trainer for cycling, running, and home strength.
        
My equipment: weights, TRX, resistance bands. No gym.
My goal: build aerobic base, maintain strength, stay injury-free.

Here are my last 30 days of workouts:
{json.dumps(workouts, indent=2)}

Give me a training plan for next week (Mon-Sun) with:
1. What to do each day (or rest)
2. Duration and key targets
3. One insight from my recent data
4. Any warnings (overtraining, gaps, etc.)

Keep it concise and practical."""
    }]
)

plan = message.content[0].text

# Save plan
with open("weekly_plan.md", "w") as f:
    f.write(f"# Week of {date.today()}\n\n{plan}")

print(plan)