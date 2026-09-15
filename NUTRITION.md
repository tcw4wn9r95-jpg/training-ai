# Nutrition — how the Food tab works

The app is a health coach, not just a training app: training, food, sleep and
recovery are read together. This file documents the food half — where every
number comes from, and what the app will and won't decide for you.

## The one rule

**Your doctor's plan is the prescription.** Whatever your clinician wrote is
stored verbatim and never overridden. Anything the plan does *not* state is
filled from published reference standards, marked as an estimate everywhere it
appears, and can be overwritten by you at any time. Coach Claudio is told the
same thing: it coaches fuelling around training, it does not practise medicine.

## Getting your plan in

**Settings (gear) → Nutrition plan.**

- **Doctor's plan** — photograph the sheet or paste its text. Claude reads it
  and extracts calorie and macro targets, the meal structure with portions,
  prescribed and restricted foods, and the method the plan follows. Anything
  the document doesn't state comes back `null`; the parser is instructed never
  to invent a number.
- **Daily targets** — the resulting baseline day, editable. Each value is
  labelled by provenance: stated in your plan, worked out from your plan's
  meals, set by you, or a reference standard.
- **About me** — weight, height, age, sex, daily activity and goal direction.
  Used to size anything the plan left out and to scale training fuel to your
  body.

Everything is stored in `nutrition_plan.json` in this repo (and in
`localStorage` so the app works offline).

## Where the reference numbers come from

Used only for values your plan didn't state.

| Target | Source |
|---|---|
| Energy | Mifflin-St Jeor resting energy equation × activity factor — the predictive equation recommended by the Academy of Nutrition and Dietetics |
| Protein | 1.2–2.0 g/kg/day for active adults (ACSM / Academy of Nutrition and Dietetics / Dietitians of Canada joint position stand, *Nutrition and Athletic Performance*, 2016); RDA floor 0.8 g/kg (IOM/NASEM Dietary Reference Intakes) |
| Carbohydrate | 3–5 g/kg light days, 5–7 g/kg moderate (~1 h/day), 6–10 g/kg endurance (1–3 h/day) — same joint position stand |
| Fat | 20–35% of energy (IOM/NASEM Acceptable Macronutrient Distribution Range), default 30% |
| Fibre | 14 g per 1000 kcal (IOM/NASEM Adequate Intake) |
| Water | EFSA adequate intake for total water — 2.5 L/day men, 2.0 L/day women, of which ~20–30% comes from food — plus 0.4–0.8 L per hour of training (ACSM position stand on exercise and fluid replacement) |
| Session energy cost | MET values from the Compendium of Physical Activities (Ainsworth et al., 2011), net of resting metabolism; measured calories from your watch are used instead when the session is already synced |

These are population reference values, not medical advice.

## Training-day fuelling

Rest day, or the training plan paused with nothing actually trained → the
baseline day is used exactly as written. Nothing is added.

When there *is* a session, the app estimates its energy cost and tops the day up:

- **Carbohydrate** takes ~60% of the extra energy, capped so total carbs stay
  within 10 g/kg.
- **Protein** gains up to 0.2 g/kg on strength days, 0.12 g/kg otherwise,
  never past 2.0 g/kg total.
- **Fat** takes whatever energy is left, capped at +15 g.
- **Water** gains 600 ml per training hour.
- **Fibre** is left alone — pushing fibre up around hard sessions is a gut
  problem, not a win.

A completed session (real data from Garmin, calories included) always beats a
planned one. That means a paused plan still gets you fuelled for a session you
actually did — the pause suppresses *planned* fuel, not real work.

## Logging what you eat

Three ways in, all of which end at the same editable ingredient list so you can
correct anything before it's saved:

1. **Type it in** — ingredients with their own numbers. The ✨ button next to a
   row asks Claude for standard food-composition values for that food and amount.
2. **Label photo** — photograph the nutrition table and say how much you ate.
   Claude reads the table as printed (handling per-100 g vs per-serving, and kJ
   → kcal) and does the portion maths, returning `null` for anything the label
   doesn't print.
3. **Meal photo** — photograph the plate. Claude identifies components,
   estimates portions and returns a confidence score. Entries below 0.7 are
   flagged *Rough* in the log, and the review note names what the photo
   couldn't see.

You can also just tell Coach Claudio ("I had chicken and rice") — it calls
`log_meal` / `log_water` and the entry lands in the same diary.

Everything is stored in `food_log.json`, keyed by date, merged per-day against
the remote copy so logging on the phone and on the laptop doesn't clobber.

## Compliance

Each macro is scored against the day's target: calories, carbs and fat as a
band (±10% is perfect, falling off either side), protein, fibre and water as a
floor (meeting it is perfect). Weighted 30/25/15/10/10/10 for
calories/protein/carbs/fat/fibre/water.

**A day in progress is never scored.** Until the day is over, the app shows
pace instead — where you are against where you'd normally be by this hour,
based on your plan's meal times — and the compliance score lands once the last
meal slot has passed. Reports and the compliance chart only use finished days.

## Reports

- **Home** — today's ring (pace while the day runs, score once it's done),
  14-day compliance chart with training days coloured separately, and the top
  insights. It keeps working when the training plan is paused.
- **Health** — the full report: 30-day averages with protein and carbs per kg,
  energy in vs energy needed, macro split, hydration, a training-days vs
  rest-days table, and the cross-domain insights.

Insights are computed from your own logged days, never generic. Each one states
its sample size, and each split needs at least three days on both sides before
it will show. They are associations in your data, not proof of cause — the
wording follows whichever direction your data actually points.
