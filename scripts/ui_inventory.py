"""Phase 14 screen inventory for USE-3 (inputs show unit and range) and USE-4 (axes have units; glossary).

    python scripts/ui_inventory.py [--out file.json]

Every screen is opened in Streamlit's AppTest in its default state, with a Stage 1 and a Stage 2 run marked as
done, in both roles. Methods fixed in BUILD_STEPS.md (Phase 14 rules) before this was run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(APP))
SCREENS = ["Home.py"] + sorted((p.relative_to(APP).as_posix() for p in (APP / "pages").glob("*.py")),
                               key=lambda s: int(s.split("/")[1].split("_")[0]))
UNIT = re.compile(r"\(([^()]+)\)\s*$")
SYMBOL = re.compile(r"(?<![A-Za-z])([A-Za-zλν][a-zA-Z]?_(?:\{[^}]+\}|[A-Za-z0-9]+)|λ_?D|Γ)")


def axis_titles(chart) -> list[tuple[str, str]]:
    spec = json.loads(chart.proto.spec)
    layout = spec.get("layout", {})
    titles = []
    for key, value in layout.items():
        if re.fullmatch(r"[xy]axis\d*", key) and isinstance(value, dict):
            title = value.get("title")
            text = title.get("text") if isinstance(title, dict) else title
            titles.append((key, text or ""))
    return titles


def inspect(screen: str, role: str) -> dict:
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(APP / screen), default_timeout=300)
    at.session_state["role"] = role
    at.session_state["has_run"] = True
    at.session_state["has_run2"] = True
    at.run()
    sliders = {s.label for s in at.slider}
    captions = " ".join(c.value for c in at.caption)
    inputs = []
    for kind, widgets in (("number_input", at.number_input), ("slider", at.slider)):
        for w in widgets:
            label, help_text = w.label, (w.help or "")
            low, high = getattr(w, "min", None), getattr(w, "max", None)
            unit = bool(UNIT.search(label)) or label in UNITLESS
            if kind == "slider" or label in sliders:
                shown = "slider"
            elif low is not None and high is not None and all(f"{v:g}" in help_text + label + captions for v in (low, high)):
                shown = "stated in label/help/caption"
            elif re.search(r"\d\s*(–|-|to)\s*\d", help_text + label) or help_text.startswith("Allowed:"):
                shown = "range stated in label/help"
            else:
                shown = ""
            inputs.append({"kind": kind, "label": label, "unit_ok": unit, "range_shown": shown})
    axes = []
    for chart in at.get("plotly_chart"):
        for key, text in axis_titles(chart):
            axes.append({"axis": key, "title": text, "unit_ok": bool(UNIT.search(text))})
    metrics = [m.label for m in at.metric]
    return {"screen": screen, "role": role, "exceptions": [str(e.value)[:200] for e in at.exception],
            "inputs": inputs, "axes": axes, "metric_labels": metrics}


UNITLESS = {"Water pH", "Initial pH", "Number of points", "Points", "Random seed", "Seed"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "ui_inventory.json"))
    args = parser.parse_args()
    os.environ["PLASMA_TWIN_DB"] = str(Path(tempfile.mkdtemp()) / "inventory.db")
    rows = [inspect(screen, role) for screen in SCREENS for role in ("Student", "Researcher")]
    # one entry per distinct input / axis (the same widget appears in both roles)
    inputs = {(r["screen"], i["label"], i["kind"]): i for r in rows for i in r["inputs"]}
    axes = {(r["screen"], a["axis"], a["title"]): a for r in rows for a in r["axes"]}
    home = (APP / "Home.py").read_text(encoding="utf-8")
    glossary = home[home.index('with st.expander("Glossary")'):]
    symbols = sorted({s for r in rows for text in [a["title"] for a in r["axes"]] + r["metric_labels"] for s in SYMBOL.findall(text)})
    missing = [s for s in symbols if s.replace("{", "").replace("}", "") not in glossary]
    summary = {
        "screens": len(SCREENS), "exceptions": {f"{r['screen']} ({r['role']})": r["exceptions"] for r in rows if r["exceptions"]},
        "numeric_inputs": len(inputs), "inputs_with_unit": sum(i["unit_ok"] for i in inputs.values()),
        "inputs_with_range_shown": sum(bool(i["range_shown"]) for i in inputs.values()),
        "inputs_missing": [f"{k[0]}: {k[1]} ({'no unit' if not v['unit_ok'] else ''}{', ' if not v['unit_ok'] and not v['range_shown'] else ''}{'no range' if not v['range_shown'] else ''})"
                           for k, v in inputs.items() if not (v["unit_ok"] and v["range_shown"])],
        "axes": len(axes), "axes_with_unit": sum(a["unit_ok"] for a in axes.values()),
        "axes_missing": [f"{k[0]}: {k[1]} '{k[2]}'" for k, a in axes.items() if not a["unit_ok"]],
        "symbols_shown": symbols, "symbols_not_in_glossary": missing,
    }
    Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
