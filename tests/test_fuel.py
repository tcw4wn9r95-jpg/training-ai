"""Run with: python -m unittest discover -s tests

fuel.py is the Python copy of the dashboard's fuelFor (used by sync.py to publish
fuel.json for NutriPrep). The parity test runs the dashboard's own JavaScript
against it, so the two can't drift apart silently.
"""
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import fuel  # noqa: E402

PLAN = {"body": {"weight_kg": 80, "height_cm": 180, "age": 38, "sex": "male", "activity": 1.55, "goal": "loss"},
        "targets": {"kcal": {"value": 2100, "src": "plan"}, "protein_g": 150}}
NP = {"kcal": 1900, "protein_g": 150, "carbs_g": 180, "fat_g": 60, "fiber_g": 30}
WORKOUTS = [
    {"date": "2026-10-05", "sport": "cycling", "duration_min": 90, "tss": 80, "calories": 1000, "avg_hr": 140},
    {"date": "2026-10-06", "sport": "running", "duration_min": 45, "tss": 60, "avg_hr": 165},
    {"date": "2026-10-07", "sport": "strength", "duration_min": 40},
    {"date": "2026-10-07", "sport": "walking", "duration_min": 30, "calories": 150},
    {"date": "2026-10-08", "sport": "tennis", "tss": 55},
]


class FuelTests(unittest.TestCase):
    def test_only_completed_sessions_and_nutriprep_base(self):
        out = fuel.build_fuel(WORKOUTS, PLAN, NP, 173)
        self.assertEqual(out["base"]["carbs_g"], 180)            # NutriPrep wins
        self.assertEqual(sorted(out["days"]), ["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"])
        d = out["days"]["2026-10-05"]
        self.assertEqual(d["src"], "measured")
        self.assertEqual(d["session_kcal"], 1000 - 80 * 1.5)       # watch kcal net of resting
        self.assertEqual(d["add"]["water_ml"], 900)
        self.assertEqual(out["days"]["2026-10-07"]["src"], "estimated")   # mixed day

    def test_rest_day_and_since(self):
        self.assertIsNone(fuel.fuel_for_day([], 80, fuel.base_targets(PLAN, NP), 173))
        self.assertEqual(list(fuel.build_fuel(WORKOUTS, PLAN, NP, 173, since="2026-10-07")["days"]),
                         ["2026-10-07", "2026-10-08"])

    def test_js_rounding(self):
        self.assertEqual(fuel.jround(2.5), 3)
        self.assertEqual(fuel.jround(-0.5), 0)


def _extract(src: str, name: str) -> str:
    m = re.search(r"\n(const|function) " + re.escape(name) + r"\b", src)
    if not m:
        raise AssertionError(f"{name} not found in dashboard.html")
    if m.group(1) == "const":                 # const X={...} or const X=[...]
        i = src.index("=", m.start()) + 1
        while src[i].isspace():
            i += 1
    else:
        i = src.index("{", m.start())
    open_c = src[i]
    close_c = {"{": "}", "[": "]"}[open_c]
    depth = 0
    for j in range(i, len(src)):
        depth += {open_c: 1, close_c: -1}.get(src[j], 0)
        if depth == 0:
            end = j + 1
            return src[m.start():end] + (";" if src[end:end + 1] == ";" else "")
    raise AssertionError(name)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ParityWithDashboardTests(unittest.TestCase):
    def test_python_matches_dashboard_fuelFor(self):
        html = (ROOT / "dashboard.html").read_text()
        parts = [_extract(html, n) for n in ("_num", "clamp", "sportOf", "MET_TABLE", "nutriBody", "bodyKg",
                                             "referenceTargets", "NUTRIPREP_KEYS", "baseTargets", "sessionHours",
                                             "intensityOf", "sessionKcal", "actualsOn", "fuelFor")]
        dates = sorted({w["date"] for w in WORKOUTS})
        js = "\n".join(parts) + f"""
var nutritionPlan={json.dumps(PLAN)}, nutriprepTargets={json.dumps(NP)}, workouts={json.dumps(WORKOUTS)};
var planPaused=false, LTHR=173; function planSessionsOn(){{return [];}}
var out={{}}; {json.dumps(dates)}.forEach(function(d){{var f=fuelFor(d); out[d]={{add:f.add,kcal:f.kcal,src:f.src}};}});
console.log(JSON.stringify(out));"""
        res = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
        self.assertEqual(res.returncode, 0, res.stderr)
        js_out = json.loads(res.stdout)
        py = fuel.build_fuel(WORKOUTS, PLAN, NP, 173)["days"]
        for d in dates:
            a = js_out[d]["add"]
            self.assertEqual({k: a[k] for k in ("kcal", "carbs_g", "protein_g", "fat_g", "water_ml")}, py[d]["add"], d)
            self.assertEqual(js_out[d]["kcal"], py[d]["session_kcal"], d)
            self.assertEqual(js_out[d]["src"], py[d]["src"], d)


if __name__ == "__main__":
    unittest.main()
