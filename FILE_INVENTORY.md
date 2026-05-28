# AthleteIQ — Complete File Inventory

All files you need to deploy the system.

## Core Application Files

### `sync.py` (18 KB)
**Main workflow script.** Runs every Sunday on GitHub Actions.

What it does:
1. Connects to Garmin Connect and fetches 6 weeks of activity data
2. Analyzes power data → detects FTP increases (via `ftp_detector.py`)
3. Analyzes running HR data → detects LTHR increases (via `lthr_detector.py`)
4. Updates `profile.json` with new zones if fitness improved
5. Calls Claude Haiku API to generate training plan
6. Outputs plan as Markdown (human-readable) and JSON (structured)
7. Parses JSON plan and pushes each workout to Garmin Connect
8. Commits results to GitHub

**Dependencies:** `garminconnect`, `anthropic`

---

### `dashboard.html` (52 KB)
**The entire app.** Runs on GitHub Pages (static site).

Tabs:
- **Home** — KPIs (CTL, ATL, TSB), PMC chart, weekly TSS, activity mix
- **Plan** — This week's workouts (collapsible cards with full details)
- **Compliance** — Session compliance tracking, recent activity
- **Availability** — Set your weekly schedule (min 30 min slots)
- **Log** — Activity history with filters (running, cycling, strength)
- **Coach** — Chat with Coach Claudio (calls Claude API directly)

Features:
- Apple Design System (no emojis, clean typography)
- Mobile-first; works as iPhone home screen app
- Reads data from `workouts.json` and `weekly_plan.md` on GitHub
- Stores GitHub + Anthropic tokens in browser localStorage
- Has SVG icons and custom logo

**Dependencies:** Chart.js (CDN), Anthropic API (direct from browser)

---

### `ftp_detector.py` (5.1 KB)
**Auto-detects FTP increases.**

Called by `sync.py` every Sunday.

Algorithm:
- Analyzes cycling workouts from last 60 days
- Finds hard efforts (power > 90% current FTP)
- Identifies most sustained effort
- Estimates new FTP = 95% of that effort's average power
- Confidence checks: min duration, min change (5W), max change per period
- Returns `None` if not confident enough

---

### `lthr_detector.py` (5.3 KB)
**Auto-detects LTHR (running threshold HR) increases.**

Called by `sync.py` every Sunday.

Algorithm:
- Analyzes running workouts from last 60 days
- Finds hard efforts (HR > 80% max HR, 15+ min duration)
- Identifies most sustained high-HR effort
- Estimates new LTHR from that effort's average HR
- Confidence checks: min duration, valid HR range (82-93% max), min change
- Returns `None` if not confident enough

---

### `coach_api.py` (4.6 KB)
**Optional backend for Coach Claudio.**

Currently the dashboard calls Claude directly from the browser (no backend needed).

If you want to deploy this:
- Uses Flask
- Stores conversation history per session
- Adds training context to each message
- Calls Claude Haiku API
- Can be deployed to Fly.io or similar

**Dependencies:** `flask`, `anthropic`

---

## Configuration Files

### `profile.json` (1.9 KB)
**Your training zones and personal metrics.**

Structure:
```json
{
  "name": "Diego",
  "running": {
    "resting_hr": 60,
    "max_hr": 196,
    "threshold_hr": 173,
    "zones": { "z1-z5": {...} }
  },
  "cycling": {
    "ftp_watts": 177,
    "zones": { "z1-z5": {...} }
  }
}
```

**Auto-updated every Sunday** by `sync.py` if FTP or LTHR changes.

---

### `availability.json` (422 bytes)
**Your weekly schedule for Claude.**

Structure:
```json
{
  "week_of": "2026-06-02",
  "days": {
    "Monday": {"available": false, "hours": 1},
    "Tuesday": {"available": false, "hours": 1},
    "Wednesday": {"available": true, "hours": 1.5},
    ...
  },
  "notes": "optional notes for Claude"
}
```

**Updated by you** on the Availability tab of the dashboard.
**Read by Claude** every Sunday when generating the plan.

---

## Generated Files (auto-created by workflow)

These are created by `sync.py` every Sunday and committed to your repo.

### `workouts.json`
Raw dump of your last 6 weeks of Garmin activities. Used by the dashboard to show activity log and calculate compliance.

### `weekly_plan.md`
Human-readable training plan. Shown on the **Plan** tab of the dashboard.

Example:
```markdown
# Training Plan — Week of 02 June 2026

### Monday — Rest Day
Easy recovery or complete rest.

### Wednesday — Running Threshold
**Sport:** Running | **Total duration:** 60 minutes

#### Warm-up (10 min)
- HR Zone 1–2 (130–162 bpm)
- Easy jog

#### Main Set (30 min)
- HR Zone 4 (173–181 bpm)
- Sustained threshold pace
- Garmin Alert: >180 bpm = too hard, back off

#### Cool-down (10 min)
- HR Zone 1 (100–130 bpm)
- Walk / easy jog
```

### `weekly_plan.json`
Structured version of the plan. Parsed by `sync.py` and pushed to Garmin as workouts.

Structure:
```json
[
  {
    "day": "Wednesday",
    "date": "2026-06-03",
    "sport": "running",
    "name": "Threshold run",
    "total_duration_secs": 3600,
    "steps": [
      {"type": "warmup", "duration_secs": 600, "target_type": "heart_rate", ...},
      {"type": "interval", "duration_secs": 1800, ...},
      {"type": "cooldown", ...}
    ]
  }
]
```

---

## GitHub Files

### `.github/workflows/weekly_plan.yml`
**GitHub Actions configuration.**

Runs every Sunday at 7pm UTC (8pm Luxembourg) or on-demand via workflow_dispatch.

Steps:
1. Check out code
2. Set up Python 3.11
3. Install `garminconnect` and `anthropic`
4. Run `sync.py` (with secrets: GARMIN_EMAIL, GARMIN_PASSWORD, ANTHROPIC_API_KEY)
5. Commit results if anything changed

**You need to create this file** in `.github/workflows/` folder in your repo.

---

### `.gitignore`
Standard Python gitignore. Ignores:
- `__pycache__/`
- `*.pyc`
- `venv/`
- `.env`

---

## Documentation

### `README.md` (11 KB)
**Complete system documentation.**

Covers:
- Features & architecture
- Full setup instructions
- How each component works
- Auto-detection algorithms
- Troubleshooting

---

### `QUICKSTART.md` (2.7 KB)
**10-minute setup guide.**

Step-by-step:
1. Fork repo
2. Add GitHub secrets
3. Update dashboard config
4. Push
5. Configure dashboard
6. Set availability
7. Run workflow
8. Check Garmin
9. Add to iPhone

---

### `FILE_INVENTORY.md` (this file)
**What every file does and why it matters.**

---

## Deployment Checklist

- [ ] Fork repo on GitHub
- [ ] Clone to your Mac: `git clone https://github.com/YOUR_USERNAME/training-ai.git`
- [ ] Add GitHub secrets (3): GARMIN_EMAIL, GARMIN_PASSWORD, ANTHROPIC_API_KEY
- [ ] Update `dashboard.html` line ~27: change GITHUB_USER to your username
- [ ] Create `.github/workflows/weekly_plan.yml` (copy from FILE_INVENTORY section)
- [ ] Create `.gitignore` (copy from FILE_INVENTORY section)
- [ ] Push everything: `git add . && git commit -m "Setup" && git push`
- [ ] Enable GitHub Pages: Settings → Pages → deploy from `main` branch
- [ ] Open dashboard URL → add GitHub token + Anthropic key in setup
- [ ] Set availability → save to GitHub
- [ ] Run workflow manually → check Garmin Connect

---

## File Size Summary

| File | Size | Purpose |
|------|------|---------|
| dashboard.html | 52 KB | The app (frontend only) |
| sync.py | 18 KB | Main workflow |
| coach_api.py | 4.6 KB | Optional backend |
| lthr_detector.py | 5.3 KB | Running HR analysis |
| ftp_detector.py | 5.1 KB | Cycling power analysis |
| profile.json | 1.9 KB | Your zones (auto-updates) |
| availability.json | 422 B | Your schedule |
| README.md | 11 KB | Full docs |
| QUICKSTART.md | 2.7 KB | 10-min setup |
| **Total** | **~100 KB** | Everything you need |

Your repository will be ~100 KB total (after first Garmin sync, workouts.json may be 5–20 KB depending on how much data you have).

---

## What's NOT Included

- Your Garmin data (fetched live from Garmin Connect each Sunday)
- Your Anthropic API key (stored in browser localStorage, not in repo)
- Your GitHub personal access token (stored in browser localStorage, not in repo)
- Coach Claudio conversation history (stored in memory only, not persisted)

---

## Questions?

- **Setup stuck?** → Check QUICKSTART.md
- **How does X work?** → Check README.md
- **Workflow failed?** → Check GitHub Actions log (Actions → Weekly Training Plan → last run)
- **Coach Claudio not working?** → Make sure you added your Anthropic key in setup drawer
