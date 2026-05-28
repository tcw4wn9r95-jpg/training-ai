# Quick Start — 10 Minutes

Get AthleteIQ running in one shot.

## 1. Prerequisites (2 min)

Have ready:
- Your Garmin Connect email & password
- Your GitHub username
- Your Anthropic API key (free tier fine: get from https://console.anthropic.com/account/keys)

## 2. Fork & Clone (2 min)

```bash
# Go to https://github.com/tcw4wn9r95-jpg/training-ai
# Click Fork (top right)
# Then on your fork:

git clone https://github.com/YOUR_USERNAME/training-ai.git
cd training-ai
```

## 3. Add Secrets (2 min)

Go to your repo on GitHub → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these three:

| Name | Value |
|------|-------|
| `GARMIN_EMAIL` | your@garmin.com |
| `GARMIN_PASSWORD` | your garmin password |
| `ANTHROPIC_API_KEY` | sk-ant-... (from Anthropic console) |

## 4. Update Dashboard Config (1 min)

Open `dashboard.html` in VS Code. Find line ~27:

```javascript
const GITHUB_USER = "YOUR_GITHUB_USERNAME";
```

Replace with your GitHub username:

```javascript
const GITHUB_USER = "yourname";
```

Save.

## 5. Push & Deploy (2 min)

```bash
git add .
git commit -m "Setup AthleteIQ"
git pull origin main --rebase
git push
```

Go to your repo → **Settings** → **Pages** → change to `main` branch.

Your dashboard is now live at:
```
https://YOUR_USERNAME.github.io/training-ai/dashboard.html
```

## 6. Configure Dashboard (1 min)

Open your dashboard URL. Tap ⚙ icon:

- **GitHub token**: https://github.com/settings/tokens/new (check `repo` box) → copy → paste
- **Anthropic API key**: paste your key from Anthropic console

Tap Save for each.

## 7. Set Availability (1 min)

Tap **Availability** in bottom nav. Check which days you're available and how many hours. Tap **Save to GitHub**.

Example:
- Monday: OFF
- Wednesday: 1.5 hours
- Thursday: 1 hour
- Saturday: 2 hours
- Sunday: 1.5 hours

## 8. Run the Workflow (3 min)

Go to **Actions** → **Weekly Training Plan** → **Run workflow** → **Run workflow**

Wait 2-3 minutes. You'll see:
- ✓ Garmin data synced
- ✓ FTP/LTHR checked
- ✓ Plan generated
- ✓ Workouts pushed to Garmin

## 9. Check Garmin Connect

Open Garmin Connect app → **Training** → **Workouts**

You should see this week's sessions with:
- Full step-by-step structure
- HR or power targets
- Warm-up / main set / cool-down

## 10. Add to iPhone (optional)

Safari → your dashboard URL → Share → Add to Home Screen

AthleteIQ appears as an app icon.

---

## Now What?

- **Coach Claudio** — Tap Coach tab, ask training questions
- **Next Sunday** — FTP/LTHR auto-detect, new plan generates automatically
- **Stay strong** — Your zones improve as you get fitter

Questions? Check README.md for troubleshooting.
