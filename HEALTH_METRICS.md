# Health & Recovery — Benchmark Analysis & Methodology

How AthleteIQ turns Garmin's daily wellness data into a Whoop-style recovery
readout, and why each metric is used the way it is.

## 1. What the leaders actually do

| Platform | Core recovery signal | Secondary inputs |
|----------|---------------------|------------------|
| **Whoop** | Overnight **HRV (RMSSD)** vs personal baseline (dominant weight) | Resting HR, respiratory rate, sleep performance, prior-day skin temp |
| **Oura** | **Readiness**: HRV balance + resting HR + body temperature | Sleep balance, recovery index, prior-day activity |
| **Garmin** | **Body Battery** (HRV + stress + activity) and **Training Readiness** | Sleep, recovery time, HRV status, acute load, stress |

The consistent theme: **compare each signal to the individual's own rolling
baseline, not population norms.** HRV and resting HR are highly personal — an
absolute HRV of 45 ms can be excellent for one athlete and poor for another.
What matters is the *deviation from your normal*.

## 2. Metrics we use, and why

Ranked by evidence strength for **daily readiness** (endurance-sport literature:
Plews, Buchheit, Stanley on HRV-guided training; Seiler on autonomic recovery):

1. **HRV (overnight RMSSD)** — the single best daily marker of autonomic
   (parasympathetic) recovery. Rising/stable vs baseline = recovered and able to
   absorb load. A meaningful drop = accumulated fatigue, stress, under-fuelling,
   or oncoming illness. **Highest weight.**
2. **Resting Heart Rate (RHR)** — inverse of HRV and a good corroborating
   signal. Elevated RHR vs baseline flags incomplete recovery or illness.
3. **Sleep** — duration **and** quality (deep + REM). The substrate for
   adaptation; Garmin's 0–100 sleep score already blends these.
4. **Body Battery (overnight charge / morning level)** — Garmin's proprietary
   energy proxy built from HRV + stress + activity. Useful, already personalised.
5. **Stress (HRV-derived, daytime avg)** — sustained high stress blunts
   adaptation and recovery.
6. **Respiratory rate** — a spike above baseline is an early illness / strain
   flag (used heavily by Whoop during the 2020s).
7. **Pulse Ox / SpO2** — mostly altitude and sleep-disordered-breathing context;
   normally 95–100%. Informational, low weight.
8. **Training Readiness / VO2max / Training Status** — if the device reports
   them, shown directly as corroboration; not required for our own score.

## 3. The recovery score (0–100)

Personal-baseline, Whoop-style. For each metric we compute a rolling baseline
(trailing ~30 days, excluding today: mean μ and standard deviation σ) and a
z-score for today, then map to a 0–100 component:

```
component = clamp( 65 + 25 * z , 0, 100 )      # +1σ ≈ 90, baseline ≈ 65, −1σ ≈ 40
```

- **HRV**: higher is better → z = (today − μ)/σ
- **RHR**: lower is better → z = (μ − today)/σ   (inverted)
- **Sleep**: Garmin sleep score used directly (already 0–100)
- **Body Battery**: morning/high value used directly (already 0–100)
- **Stress**: inverted and rescaled → 100 − stress
- **Respiration**: near baseline = fine; only *penalises* when elevated

Metrics with too little history (σ unknown / <4 samples) fall back to sensible
absolute anchors so a brand-new user still gets a reading.

**Weights** (re-normalised over whichever metrics are available on a given day):

| Metric | Weight |
|--------|-------:|
| HRV | 0.35 |
| Sleep | 0.25 |
| RHR | 0.20 |
| Body Battery | 0.10 |
| Stress | 0.07 |
| Respiration | 0.03 |

**Readiness bands** (mirrors Whoop's green/yellow/red):

| Score | Band | Guidance |
|------:|------|----------|
| ≥ 67 | **Primed** (green) | Recovered — good day for a hard/quality session |
| 34–66 | **Moderate** (yellow) | Maintain; be cautious with intensity, keep easy days easy |
| < 34 | **Low** (red) | Prioritise recovery — easy or rest, address sleep/stress |

## 4. Insights we derive

- **HRV trend**: 7-day mean vs 30-day baseline → building / stable / suppressed.
- **RHR trend**: rising RHR alongside falling HRV is a classic under-recovery /
  illness pattern → surfaced as an explicit warning.
- **Sleep debt**: 7-day average vs an 8h target.
- **Strain vs recovery balance**: pairs the recovery score with training load
  (TSB/ATL from the PMC) — high strain + low recovery = back off.
- **Illness early-warning**: HRV drop + RHR rise + respiration rise together.
- **Positive reinforcement**: consistent green recovery + rising HRV = the
  training and lifestyle are working; safe to progress.

## 5. How Coach Claudio uses it

The recovery score, HRV/RHR status and trends, sleep, Body Battery and stress
are injected into the coach's context so that:

- **When planning**, the coach bends the week to recovery — suppressed HRV or a
  string of red days → pull intensity/volume; strong recovery → green light to
  progress. Body wins over the calendar.
- **When reviewing a workout**, it reads that day's recovery to interpret the
  result (e.g. "that tempo felt hard because you were at 31% recovery — HRV was
  18% below baseline, not a fitness problem").

The weekly plan generator (`sync.py`) receives the same health summary so plans
are recovery-aware from the moment they're built.

## 6. Data source & integrity

All values come from Garmin Connect via `sync.py` (`get_hrv_data`,
`get_rhr_day`, `get_stress_data`, `get_body_battery`, `get_respiration_data`,
`get_spo2_data`, `get_training_readiness`). Every metric is fetched
best-effort and independently — if a device doesn't report one (or the API
omits it that day), that field is `null` and both the score and the UI degrade
gracefully rather than breaking. Nothing here is a medical device; it's training
guidance.
