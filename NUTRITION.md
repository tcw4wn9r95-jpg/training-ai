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
| Free sugar | under 10% of total energy (WHO guideline on sugars intake for adults and children), with the conditional further reduction below 5% shown as the stricter aim |
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

Four ways in, all of which end at the same editable ingredient list so you can
correct anything before it's saved:

1. **Type it in** — ingredients with their own numbers. The ✨ button next to a
   row asks Claude for standard food-composition values for that food and amount.
2. **Label photo** — photograph the nutrition table and say how much you ate.
   Claude reads the table as printed (handling per-100 g vs per-serving, and kJ
   → kcal) and does the portion maths, returning `null` for anything the label
   doesn't print.
3. **Describe it** — say what went in, in your own words. Built for the meals a
   camera is useless on: a smoothie stops being legible the moment it's
   blended, and you know exactly what you put in it. Rough amounts are fine —
   a handful, a scoop, a splash — and there's a second field for how much of it
   you actually had, so half a blender-full scales properly.

   Claude breaks the description into items, states what it assumed for each
   vague amount, and drops its confidence where it had to guess. It then goes
   through the same check screen as a photo (below), showing your own words back
   to you in place of the picture. Saved entries read *Described*.

4. **Meal photo** — photograph the plate. Claude identifies each component,
   estimates its portion, and returns a confidence score plus a box around each
   food and a list of what it genuinely can't tell.

   **When it isn't sure, it asks.** If overall confidence is under 75%, any one
   item is under 60%, or Claude raised a question, the photo comes back with its
   guesses drawn on it — a numbered pin and an outline per food, amber where it
   is unsure — above its own open questions ("is the protein chicken or white
   fish?"). Each item has a correction field, and there's a free-text box for
   the plate as a whole.

   Whatever you write goes into the next estimate as fact: the re-estimate
   prompt carries the previous guess, your per-item corrections and your notes,
   and instructs Claude to treat them as authoritative rather than re-identify
   what you've settled. If it comes back confident, you land straight in the
   review list; if something is still unclear, the photo comes back with the
   updated guesses and you can correct it again. Corrections are saved with the
   meal, which is why a corrected entry reads *Photo, corrected* rather than
   *Rough*.

   A confident guess can still be wrong, so the review list keeps a **Wrong
   food? Show me the photo** button that reopens the same screen.

You can also just tell Coach Claudio ("I had chicken and rice") — it calls
`log_meal` / `log_water` and the entry lands in the same diary.

Everything is stored in `food_log.json`, keyed by date, merged per-day against
the remote copy so logging on the phone and on the laptop doesn't clobber.

## Sugar

Sugar is tracked as **two** numbers, because the guidance only applies to one
of them.

- **Total sugar** is what a packet prints — it includes the sugar naturally in
  fruit, milk and plain yogurt. Your plan prescribes berries, kefir and
  yogurt, so driving this to zero would mean ignoring your own plan. It is
  shown under carbs, the way a label reads, with its share of the day's
  carbohydrate, and it carries no target.
- **Free sugar** is sugar added to food plus what comes from honey, syrups and
  fruit juice. This is the one WHO puts a line under, and the one the app
  scores: under 10% of energy, with 5% flagged as the stricter aim.

Every input route asks for both: the label reader takes total sugars off the
packet and estimates the free part from what the food is, and the photo,
describe and lookup prompts are all told the difference explicitly. Where an
entry has no sugar figure, the day simply isn't scored on sugar rather than
counting a missing number as a perfect zero — the day card says so.

Training tops up carbohydrate but never the free-sugar ceiling; quick sugars
around a session come out of the carb allowance, not a raised limit.

The Health report shows both averages across the days that recorded them, and
the insight reads them the same way: free sugar against the ceiling and how
many days went over, total sugar as context that isn't a failure.

## Asking what to eat

The Food tab's top card — **What should I eat now?** — turns the day's
remaining numbers into an answer rather than a report. It opens on where the
day stands: what's eaten, what's left of each macro, which meal is next by your
plan's own meal times, and whether training has topped the targets up.

Two ways to use it:

- **Suggest a meal.** Optionally say what you have in or how long you've got.
  You get two or three options, each with its ingredients and amounts, why it
  fits what's still missing, roughly how long it takes, how it sits with your
  plan, and what it leaves for the rest of the day. The totals under each
  option are computed by the app from the ingredients, not taken on trust from
  the model.

- **Check my idea.** Say what you're thinking of eating, and what you have
  available. You get a verdict — works as is, needs a tweak, worth a rethink —
  then what to **add** and what to **drop or cut down**, each with a reason,
  and the final list of what to actually eat. Additions only come from what you
  said you have. It never tells you to skip the meal.

Either way, **Log this meal** drops the result into the normal meal sheet,
pre-filled and pre-slotted by the time of day, so it saves through the same
review path as everything else and shows up as *Coach suggested*. **Edit
first** does the same without saving, for when you ate three quarters of it.

The prompt carries your remaining macros, the time, the meal your plan expects
next, its prescribed portions for that meal, your plan's method, and its
restricted foods — which are never suggested, and are flagged if you propose
one yourself.

## What's in the pot

Before serving, not after eating. **In the pot** is the fifth way to add food —
it sits with *Type in*, *Describe*, *Label* and *Photo* in the **Add to…** sheet,
behind the **+ Add** on any meal. Photograph the pan, the tray or the pot, and
the coach tells you how much of it to put on your plate to hit what's left of
the day.

It reads the food two ways, and says which one it chose:

- **Mixed — weigh it.** A stir-fry, a fried rice, a stew, a bake: things you
  can't separate on the plate. You get a single number in grams — *serve 320 g* —
  with the per-100 g macros it was derived from, and a line telling you how to
  get there: bowl on the scale, zero it, spoon in until it reads 320 g. The
  totals for that serving are computed by the app from the per-100 g figures and
  the grams, so the number and the macros can never disagree.

- **Separate — by item.** Chicken, rice and greens in three pans. You get a
  weight per component, each with its own calories, plus a plain-language version
  for when there's no scale — *one thigh and a bit, a heaped half-cup of rice*.

Either way the card carries the totals for the serving, why it was portioned
that way against today's gap, and what it leaves for the rest of the day.

**− / +** step the mixed serving by 25 g and everything above rescales live, for
when you want a bit more or you've already decided 300 is enough.

A photo can't see the oil, or what's underneath. The **what went in** box is
optional but does most of the work: say *300 g rice, 500 g chicken thigh, 3 eggs,
2 tbsp oil* and the weights stop being guesses. When Claudio is still unsure he
says so on the card and asks — *how much oil went into the wok?* — and the
correction box feeds straight back into a recalculation, the same loop as the
photo and describe inputs.

**Serve this much** hands the portion to the same review list the other four
inputs end in, pre-filled and carrying the grams you actually settled on rather
than the first number suggested. Change anything the scale disagreed with, then
**Save to my day** files it against the meal you opened the sheet on, marked
*Portioned from the pot*.

## Opening a meal

Tap any logged meal and it opens into its components. Each one shows its
amount, its calories and its share of the meal, a bar splitting its energy
between protein, carbohydrate and fat, and the grams of each including fibre.
Under that, the meal's total is drawn against the day's targets — what this one
meal was worth as a percentage of each, training top-up included.

The last block is provenance: where the numbers came from (a photo, your
description, a packet label, a chat with the coach, or typed in), the time it
was logged, the confidence and how many correction rounds it took, what you
corrected, and what Claude assumed. A meal logged with only a total and no
breakdown says so rather than inventing components.

## Compliance

Each macro is scored against the day's target: calories, carbs and fat as a
band (±10% is perfect, falling off either side), protein, fibre and water as a
floor (meeting it is perfect). Weighted 30/25/15/10/10/10 for
calories/protein/carbs/fat/fibre/water.

**A day in progress is never scored.** Until the day is over, the app shows
pace instead — where you are against where you'd normally be by this hour,
based on your plan's meal times — and the compliance score lands once the last
meal slot has passed. Reports and the compliance chart only use finished days.

## Appearance

The app follows your iPhone's Light/Dark setting, switching live when the phone
does (including the automatic sunset switch). Settings → Appearance can pin
Light or Dark instead; "Match iOS" is the default and hands control back to the
system.

The whole UI is driven by one set of CSS custom properties defined per theme,
so light mode is a real palette (darker accents that hold their contrast on a
warm card) rather than an inverted dark one. Both palettes are warm-toned —
warm paper in the light, warm charcoal in the dark, with a sunrise tint at the
top of the page. Charts rebuild their colours and
repaint whenever the theme changes, and a pinned theme is applied before the
first paint so the app never flashes the wrong one on launch.

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
