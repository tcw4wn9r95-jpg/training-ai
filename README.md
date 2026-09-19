# AthleteIQ — Free AI Health Coach

Your personal AI health coach: training, food and recovery in one app. Automatic
training plans, food-plan tracking against what your doctor prescribed,
hydration, and reports that read all of it together — powered by your Garmin
Fenix and Claude AI.

The app has five tabs: **Home** (the day and the trends), **Training** (plan and
completed activity), **Food** (macros, meals and water), **Health** (recovery and
the full nutrition report) and **Coach**.

Home opens the way the best health apps do: a greeting, then three rings —
**Recovery**, **Fuel**, **Training** — that say how today is going across all
three pillars at a glance, then one card naming the single most useful thing to
do next. Detail and trends sit below that; nothing static holds the top of the
screen.

## Features

### Food & nutrition
- **Your doctor's plan, in the app** — photograph the sheet your doctor or dietitian gave you, or paste its text; Claude reads out the calorie and macro targets, the meal structure, and the prescribed and restricted foods (Settings → Nutrition plan)
- **Only reputable sources fill the gaps** — anything your plan doesn't state comes from published standards (Mifflin-St Jeor, ACSM/AND/DC, IOM/NASEM DRI, EFSA, WHO), is labelled as an estimate everywhere it appears, and can be overwritten; your clinician's numbers are never overridden (see `NUTRITION.md`)
- **Fuel that follows your training** — on a training day the targets are topped up for the session (carbs first, protein on strength days, extra fluid); on a rest day, or with the plan paused and nothing trained, the baseline is left exactly as prescribed
- **Five ways to log a meal** — type the ingredients in, describe what went in and let Coach Claudio work it out (built for smoothies and anything else a photo can't show), photograph the nutrition label and say how much you ate, photograph the plate for an AI estimate, or photograph the pot before you serve and be told how much to put on the plate; every route ends in the same editable list you check before saving, and AI estimates carry a confidence flag
- **It asks when it can't tell** — an uncertain estimate comes back for checking: a photo with Claudio's guesses drawn on it pin by pin, a description with your own words and what he assumed from them, both next to the questions he can't answer; correct any of it in your own words and the macros are worked out again from what you actually ate
- **"What should I eat now?"** — the Food tab reads the time of day and what the day still owes you, and either suggests two or three meals you can actually make (optionally from what's in your fridge), or takes the meal you already have in mind and tells you what to add to it and what to leave off; one tap logs the result
- **"In the pot"** — the one input that runs *before* the meal, sitting with the other four behind **+ Add**: one weight for anything mixed (a fried rice, a stew, a bake) with the per-100 g numbers behind it and a −/+ stepper to adjust in 25 g steps, or a weight per component when the foods are separate; say what went in and the weights stop being guesses, and it lands in the same review list as the other inputs, carrying the grams you actually settled on
- **Open a meal, see the parts** — tapping a logged meal breaks it into its components: each one's amount, calories, share of the meal and macro split, then the meal's total against the day's targets, then where the numbers came from and what was assumed
- **Sugar, split properly** — total sugar (which includes the fruit and dairy your plan prescribes) is shown under carbs as context, while free sugar (added, plus honey, syrup and juice) carries the WHO ceiling of 10% of energy and is what the compliance score judges; days with no sugar figure are left out of that score rather than counted as zero
- **A coach’s verdict, not a readout** — the line under a meal you’re logging reads the food against the rest of your day, your training and your plan’s avoid list, and says what a friend would say about it: encouraging when it earns it, and cheerfully merciless when you’ve gone looking for trouble; it updates as you type, with no model call
- **Plan a meal before you eat it** — log any meal as planned instead of eaten, through any of the same five inputs; it never counts as eaten, but it is held against the day and the meals you haven’t decided on are re-cut around it by your plan’s own meal weights, so a heavy lunch trims breakfast and dinner in proportion and each still says what it has to spend
- **Overshoot is visible** — go past a target and the bar rescales rather than sitting at full: the target line stays where it falls and the excess is drawn beyond it, striped, in amber or red for a band or a ceiling and in green for a floor you were meant to pass
- **Water tracking** — daily target including the training top-up, with one-tap logging
- **Compliance you can trust** — a day in progress shows pace, not a score; the score lands when the day is done
- **Cross-domain insights** — how protein, hydration, meal timing and fuelling line up with your HRV, resting HR, sleep and training load, computed from your own days with the sample size stated

### Training
- **Automatic Training Plans** — Claude generates weekly plans based on your Garmin data and availability
- **Science-Based Only** — every plan follows established exercise science (progressive overload ≤10%/week, 80/20 polarised intensity, NSCA strength principles); no fads
- **Home Equipment Hard Restriction** — strength sessions only ever use what's at home (dumbbells 4/6/11/16/20 kg, TRX, bands, bodyweight); plans naming gym equipment are rejected and regenerated
- **Warm-up & Stretch Guides** — every session card opens a video/how-to section with dynamic warm-up drills and post-session static stretches
- **Built-in Activity Timer** — tap any step duration or timed stretch to get a pop-up countdown preset to the right time, with a beep and vibration when done
- **Streaks & Badges** — weekly training streak, milestone badges and habit nudges on the Home tab
- **Health Report** — a Whoop-style Health tab: a personal-baseline recovery score (0–100) from HRV, resting HR, sleep, Body Battery and stress, with trends and plain-language insights (see `HEALTH_METRICS.md`), plus the full nutrition report alongside it; Coach Claudio reads all of it when planning and when reviewing your sessions
- **Auto-Detecting Fitness** — FTP and LTHR update automatically as you get stronger
- **Garmin Integration** — Workouts push directly to your Fenix with step-by-step guidance
- **Coach Claudio** — In-app AI coach for daily training and fuelling questions; tell it what you ate and it logs it for you
- **Performance Dashboard** — PMC (Performance Management Chart), TSS, compliance tracking
- **Light & Dark, matched to iOS** — follows your iPhone's appearance setting, switching with it live (including the automatic sunset switch); Appearance in Settings can pin Light or Dark instead
- **Mobile-First** — Works perfectly on iPhone; add to home screen as an app

## System Architecture

```
Every Sunday 8pm Luxembourg Time:
┌─────────────────────────────────────────────┐
│ GitHub Actions Workflow                     │
├─────────────────────────────────────────────┤
│ 1. sync.py runs on GitHub servers          │
│    • Fetches your Garmin data (6 weeks)    │
│    • Auto-detects FTP from power data      │
│    • Auto-detects LTHR from running HR     │
│    • Updates profile.json                  │
│                                             │
│ 2. Calls Claude Haiku API                  │
│    • Reads your availability               │
│    • Generates weekly plan (markdown)      │
│    • Outputs structured JSON for workouts  │
│                                             │
│ 3. Pushes workouts to Garmin Connect       │
│    • Running workouts with HR targets      │
│    • Cycling workouts with power targets   │
│    • Scheduled for correct dates           │
│                                             │
│ 4. Commits results to GitHub               │
│    • workouts.json (your Garmin data)     │
│    • weekly_plan.md (human-readable)       │
│    • weekly_plan.json (structured)         │
│    • profile.json (updated zones)          │
└─────────────────────────────────────────────┘

Your Dashboard (GitHub Pages):
┌─────────────────────────────────────────────┐
│ dashboard.html reads from GitHub            │
│ • Fetches workouts.json & weekly_plan.md   │
│ • Shows PMC, compliance, activity log       │
│ • Lets you set availability                 │
│ • Coach Claudio (calls Claude directly)    │
└─────────────────────────────────────────────┘
```

## Setup

### Prerequisites
- Garmin Fenix watch
- GitHub account (free)
- Anthropic API key ($0.80 per million input tokens)
- 30 minutes

### Step 1 — Fork the repo

Go to https://github.com/tcw4wn9r95-jpg/training-ai and click **Fork**. Clone it to your Mac:

```bash
git clone https://github.com/YOUR_USERNAME/training-ai.git
cd training-ai
```

### Step 2 — Set up GitHub secrets

Go to your forked repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add three secrets:
- `GARMIN_EMAIL` — your Garmin Connect email
- `GARMIN_PASSWORD` — your Garmin Connect password
- `ANTHROPIC_API_KEY` — your Anthropic API key (get from https://console.anthropic.com/account/keys)

### Step 3 — Enable GitHub Actions

Go to **Actions** → **Weekly Training Plan** → **Enable workflow**

### Step 4 — Update dashboard config

Edit `dashboard.html` in VS Code. Find this line near the bottom of the script:

```javascript
const GITHUB_USER = "YOUR_GITHUB_USERNAME";
```

Change it to your GitHub username:

```javascript
const GITHUB_USER = "yourname";
```

### Step 5 — Push and enable Pages

```bash
git add .
git commit -m "Initial setup"
git pull origin main --rebase
git push
```

Go to repo **Settings** → **Pages** → set to deploy from `main` branch. Your dashboard will be live at:

```
https://YOUR_USERNAME.github.io/training-ai/dashboard.html
```

### Step 6 — Configure the dashboard

Open your dashboard URL. Tap ⚙ (gear icon):
- **GitHub token**: Create a personal access token at https://github.com/settings/tokens/new (needs `repo` scope) and paste it
- **Anthropic API key**: Paste your Anthropic key from console.anthropic.com

### Step 7 — Set your availability

Tap **Availability** in the bottom nav. Set which days you're available and how many hours per day (minimum 30 min). Tap **Save to GitHub**.

Claude will read this every Sunday and build a plan around exactly those days.

### Step 8 — Run the workflow

Go to **Actions** → **Weekly Training Plan** → **Run workflow**. Wait for it to finish (2-3 minutes).

Check **Garmin Connect** on your phone → **Training** → **Workouts**. You should see this week's sessions with full step-by-step targets.

### Step 9 — Add to iPhone home screen

Open Safari → go to your dashboard URL → tap **Share** → **Add to Home Screen**. The AthleteIQ logo appears as an app icon.

---

## Files Explained

| File | Purpose |
|------|---------|
| `sync.py` | Main workflow. Fetches Garmin data, detects FTP/LTHR, calls Claude, pushes to Garmin |
| `ftp_detector.py` | Analyzes power data, estimates FTP increases |
| `lthr_detector.py` | Analyzes running HR data, estimates LTHR increases |
| `dashboard.html` | The app. Runs on GitHub Pages, calls Claude for coaching |
| `coach_api.py` | Optional backend for Coach Claudio (can be deployed to Fly.io later) |
| `profile.json` | Your zones, FTP, LTHR — auto-updates weekly |
| `availability.json` | Your weekly schedule for Claude |
| `.github/workflows/weekly_plan.yml` | GitHub Actions config — runs every Sunday 8pm |

---

## How It Works

### Auto-Detecting FTP

Every Sunday, `sync.py` analyzes your last 60 days of cycling data:
1. Finds hard efforts (power > 90% current FTP)
2. Identifies the most sustained high-power effort
3. Estimates new FTP conservatively (95% of that effort's average power)
4. Updates zones only if confident + improvement ≥ 5W

Example: If you sustained 185W for 20 minutes, new FTP = 185 × 0.95 = 175.75 → 176W.

**Confidence checks:**
- Minimum 5-minute sustained effort
- Change must be ≥ 5W (ignores noise)
- Capped at +10W per 8 weeks (conservative)

### Auto-Detecting LTHR

Same logic for running:
1. Finds hard running efforts (tempo, threshold pace)
2. Looks for sustained HR 15+ minutes at high intensity
3. Estimates LTHR from highest sustained avg HR
4. Updates zones if confident + change ≥ 2 bpm

**Confidence checks:**
- Minimum 15-minute sustained effort
- Must be 82–93% of max HR (physiologically valid)
- Capped at ±3 bpm per 8 weeks

### Claude's Weekly Plan

Every Sunday, Claude:
1. Reads your **availability** (which days, how many hours)
2. Reads your **Garmin data** (last 6 weeks of activities, TSS, zones)
3. Generates **detailed plan** with:
   - Warm-up / main set / cool-down for each session
   - HR zones or power targets
   - Pace targets for running
   - Garmin alert settings
   - RPE (Rate of Perceived Exertion)
   - Coaching notes

4. Outputs two formats:
   - **weekly_plan.md** — human-readable (shown on dashboard)
   - **weekly_plan.json** — structured (pushed to Garmin)

### Coach Claudio

Tap **Coach** in the dashboard. Ask Claude anything:
- "Should I do the workout today?"
- "How's my fitness trending?"
- "I'm preparing for a race in 6 weeks, what should I focus on?"
- "My legs feel heavy, should I rest?"

Claude sees:
- Your training this week (TSS, volume, sports)
- Your profile (FTP, LTHR, zones)
- This week's plan

Responses are fast (~5 seconds) and personalized to your data.

---

## Costs

| Component | Cost | Notes |
|-----------|------|-------|
| Garmin Fenix | One-time | You already own |
| GitHub | Free | Unlimited Actions for public repos |
| Garmin Connect | Free | Official app |
| Anthropic API | ~$2/month | 0.80/M tokens input, 4/M tokens output |
| **Total** | **~$2/month** | Less than a coffee |

Weekly plan generation: ~50K tokens → $0.24
Each Coach message: ~5K tokens → $0.024

---

## Troubleshooting

### "No workouts on Garmin Connect"

This usually means no availability was set. Claude needs to know when you're available to generate a plan.

**Fix:**
1. Open dashboard → **Availability** tab
2. Tap at least 3 days to set them available
3. Tap **Save to GitHub**
4. Run the workflow again

Check the GitHub Actions log to see what Claude received.

### "My FTP didn't update even though I did hard efforts"

FTP only updates when:
- Duration ≥ 5 minutes at high power
- Change ≥ 5W (noise filtering)
- Confidence ≥ 30%
- Not more than +10W per 8 weeks

If your recent efforts were too short or not much harder than current FTP, it won't change.

### "Coach Claudio says 'Invalid API Key'"

You haven't added your Anthropic API key to the dashboard.

**Fix:**
1. Tap ⚙ (gear icon)
2. Paste your key in "Anthropic API key" field
3. Tap Save

### "Workflow failed — 'MFA required'"

Garmin has 2-factor authentication enabled. Unfortunately, the `garminconnect` library doesn't support MFA.

**Fix:** Temporarily disable 2FA on your Garmin account before running the workflow, then re-enable it.

---

## Advanced: Deploying Coach Backend

By default, Coach Claudio calls Claude directly from your browser (your API key is stored locally). If you want the backend server-side:

```bash
# Install Fly CLI
brew install flyctl

# In your training-ai folder
fly launch
fly deploy

# Update dashboard.html
# Find: const COACH_API = "...";
# Change to your Fly URL
```

This keeps your API key secure on the server instead of in the browser.

---

## What's Next?

- **Telegram bot** — Ask Coach Claudio via Telegram instead of the app
- **Strava sync** — Push completed workouts to Strava automatically
- **Race prediction** — Claude forecasts your race fitness based on training
- **Nutrition coaching** — Track calories/hydration alongside training
- **Mental training** — Coach helps with race day psychology

---

## Support & Contributing

This is a personal project. If you find issues:
1. Check the GitHub Actions log (Actions → Weekly Training Plan → last run)
2. Test manually: `python3 sync.py` in the `training-ai` folder
3. Check Garmin Connect app to verify data is syncing

---

**Made with ⚡ for endurance athletes who want data-driven training without the price tag.**

Stay strong. Train smart. 🚴‍♂️🏃
