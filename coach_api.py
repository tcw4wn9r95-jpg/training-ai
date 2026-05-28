"""
Coach Claudio - In-app AI coaching for AthleteIQ.

This can be deployed as a server, but for now works via direct API calls from the dashboard.
The dashboard sends messages directly to the Anthropic API with training context.

If you want to deploy this as a backend:
- Deploy to Fly.io: `fly launch` then `fly deploy`
- Set env var: ANTHROPIC_API_KEY
- Update dashboard COACH_API URL to your deployment
"""

from flask import Flask, request, jsonify
import json
import os
from datetime import date, timedelta
from anthropic import Anthropic

app = Flask(__name__)
client = Anthropic()

# Store conversation history per user session
conversations = {}

def get_training_context(workouts, profile, plan_text=""):
    """Build a summary of recent training for context."""
    if not workouts:
        return "No training data available yet."
    
    # Last 7 days
    cutoff = date.today() - timedelta(days=7)
    recent = [w for w in workouts if date.fromisoformat(w.get("date", "2000-01-01")) >= cutoff]
    
    total_tss = sum(w.get("tss", 0) or 0 for w in recent)
    total_km = sum(w.get("distance_km", 0) or 0 for w in recent)
    
    sports_count = {}
    for w in recent:
        sport = w.get("sport", "unknown")
        sports_count[sport] = sports_count.get(sport, 0) + 1
    
    context = f"""## Your Training This Week
- Total TSS: {total_tss}
- Total distance: {total_km:.1f} km
- Workouts: {", ".join(f"{count} {sport}" for sport, count in sports_count.items()) or "none yet"}

## Your Profile
- FTP: {profile.get("cycling", {}).get("ftp_watts", "?")}W
- LTHR: {profile.get("running", {}).get("threshold_hr", "?")} bpm
- Max HR: {profile.get("running", {}).get("max_hr", "?")} bpm
- Resting HR: {profile.get("running", {}).get("resting_hr", "?")} bpm"""
    
    if plan_text:
        context += f"\n\n## This Week's Plan\n{plan_text[:400]}..."
    
    return context

@app.route("/coach", methods=["POST"])
def coach_message():
    """
    Handle incoming coach messages.
    Expects: {
        "message": "user question",
        "session_id": "unique session id",
        "workouts": [...],
        "profile": {...},
        "plan": "plan text"
    }
    """
    try:
        data = request.json
        user_msg = data.get("message", "").strip()
        session_id = data.get("session_id", "default")
        workouts = data.get("workouts", [])
        profile = data.get("profile", {})
        plan = data.get("plan", "")
        
        if not user_msg:
            return jsonify({"error": "No message provided"}), 400
        
        # Initialize conversation for this session
        if session_id not in conversations:
            conversations[session_id] = []
        
        # Build context
        context = get_training_context(workouts, profile, plan)
        
        # System prompt
        system_prompt = f"""You are Coach Claudio, Diego's personal AI running and cycling coach. You have expertise in:
- Training periodization and programming
- Running and cycling physiology
- Performance analysis and pacing
- Recovery and fatigue management
- Race strategy
- Nutrition and hydration for endurance

Diego's current context:
{context}

Your style: Friendly, direct, data-driven. Use his training data to inform advice. Keep responses concise (2-3 sentences) unless he asks for detail. Address him by name occasionally. Be encouraging but honest about effort levels."""
        
        # Add user message to history
        conversations[session_id].append({
            "role": "user",
            "content": user_msg
        })
        
        # Get response from Claude
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=system_prompt,
            messages=conversations[session_id]
        )
        
        assistant_msg = response.content[0].text
        
        # Add to history
        conversations[session_id].append({
            "role": "assistant",
            "content": assistant_msg
        })
        
        # Keep only last 15 exchanges to save tokens
        if len(conversations[session_id]) > 30:
            conversations[session_id] = conversations[session_id][-30:]
        
        return jsonify({
            "response": assistant_msg,
            "session_id": session_id,
            "status": "ok"
        })
    
    except Exception as e:
        return jsonify({"error": str(e), "status": "error"}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "coach": "claudio"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
