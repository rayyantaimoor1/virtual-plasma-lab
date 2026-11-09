"""Phase 14 measurements: performance (PER), reliability (REL-1, REL-3, REL-4), ACC-3 and SEC-1.

    python scripts/measure_phase14.py            # every part (about 15-25 minutes)
    python scripts/measure_phase14.py per rel1   # only some parts

The methods and pass marks were fixed in BUILD_STEPS.md (Phase 14 rules) before this script was run.
Results are merged into docs/validation/phase14_measurements.json (timings and counts only, no private data).
"""
from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Callable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "validation" / "phase14_measurements.json"
SEED = 20261109
PYTHON = sys.executable


def timed(function: Callable[[], Any]) -> tuple[float, Any]:
    started = time.perf_counter()
    value = function()
    return time.perf_counter() - started, value


def p95(values: list[float]) -> float:
    return float(np.percentile(values, 95))


def stage1_draws(count: int) -> list[dict[str, Any]]:
    """Configurations drawn uniformly across the Stage 1 envelope (PER-1)."""
    from plasma_twin.config.loader import load_envelope
    from plasma_twin.services import stage1
    env = load_envelope()["stage1"]
    rng = np.random.default_rng(SEED)
    configs = []
    for _ in range(count):
        configs.append({**stage1.default_config(),
                        "rf_power_w": float(rng.uniform(env["rf_power_w"]["min"], env["rf_power_w"]["max"])),
                        "pressure_mbar": float(rng.uniform(env["pressure_mbar"]["min"], env["pressure_mbar"]["max"])),
                        "ar_flow_sccm": float(rng.uniform(env["ar_flow_sccm"]["min"], env["ar_flow_sccm"]["max"])),
                        "mixture": str(stage1.MIXTURES[int(rng.integers(4))]),
                        "n2_percent": float(rng.uniform(1, 10)), "o2_percent": float(rng.uniform(1, 10)),
                        "eedf": ("Druyvesteyn", "Maxwellian")[int(rng.integers(2))]})
    return configs


# ------------------------------------------------------------------------------------ PER
def per() -> dict[str, Any]:
    from plasma_twin.oes.spectrum import SpectrometerSettings, spectrum_for
    from plasma_twin.probe.analysis import ProbeAnalysisError, analyse_curve
    from plasma_twin.probe.iv_model import ProbeSettings, generate, plasma_from
    from plasma_twin.services import stage1, stage2
    from plasma_twin.stage1.profile1d import axial_profile
    out: dict[str, Any] = {}
    configs = stage1_draws(100)
    stage1.run(stage1.default_config())  # imports and the rate tables (built once per program run)

    times, results = [], []
    for config in configs:
        started = time.perf_counter()
        result = stage1.run(config)
        stage1.summarise(result)
        times.append(time.perf_counter() - started)
        results.append(result)
    times_1d = []
    for config in configs[:20]:
        started = time.perf_counter()
        result = stage1.run({**config, "spatial": "0D+1D"})
        stage1.summarise(result)
        axial_profile(result)
        times_1d.append(time.perf_counter() - started)
    out["PER-1"] = {"runs_0d": len(times), "p95_0d_s": p95(times), "max_0d_s": max(times), "median_0d_s": float(np.median(times)),
                    "runs_0d_1d": len(times_1d), "p95_0d_1d_s": p95(times_1d), "max_0d_1d_s": max(times_1d),
                    "pass": p95(times) <= 2.0 and p95(times_1d) <= 5.0}

    plasmas = [stage1.run(stage1.default_config())] + results[:4]
    spectrum_times, points = [], []
    for plasma in plasmas:
        seconds, spectrum = timed(lambda p=plasma: spectrum_for(p, SpectrometerSettings(0.005, 300.0, 900.0, 1.0)))
        spectrum_times.append(seconds)
        points.append(len(spectrum.wavelength_nm))
    out["PER-2"] = {"times_s": spectrum_times, "max_s": max(spectrum_times), "points": points, "pass": max(spectrum_times) <= 3.0}

    probe_times, failures = [], []
    settings = ProbeSettings.defaults(sweep_start_v=-100.0, sweep_end_v=100.0, sweep_step_v=0.1)
    for plasma in plasmas:
        started = time.perf_counter()
        curve = generate(plasma_from(plasma), settings)
        try:
            analyse_curve(curve)
        except ProbeAnalysisError as problem:  # E11: the analysis stops with a message; its time still counts
            failures.append(str(problem))
        probe_times.append(time.perf_counter() - started)
    out["PER-3"] = {"points": int(len(settings.voltages())), "times_s": probe_times, "max_s": max(probe_times),
                    "analysis_messages": failures, "pass": max(probe_times) <= 2.0}

    import plasma_twin.stage1.sweep as sweep_module
    original, point_times = sweep_module.solve, []

    def timed_solve(inputs):
        started = time.perf_counter()
        try:
            return original(inputs)
        finally:
            point_times.append(time.perf_counter() - started)

    sweep_module.solve = timed_solve
    try:
        total, points_ = timed(lambda: sweep_module.sweep(stage1.to_inputs(stage1.default_config()), "rf_power_w",
                                                          np.linspace(10, 100, 200)))
    finally:
        sweep_module.solve = original
    out["PER-4"] = {"points": len(points_), "solved": sum(p.solved for p in points_), "total_s": total,
                    "longest_point_s": max(point_times),
                    "progress_shown": "a spinner while the whole sweep runs (no per-point progress bar on M3)",
                    "pass_total": total <= 120.0, "pass": False,
                    "note": "the SRS asks for progress updated at least every 2 s; M3 shows a spinner, not progress"}

    rng = np.random.default_rng(SEED)
    s2 = [stage2.default_config()]
    gases = ("O2 + water vapour", "O2 only")
    for _ in range(9):
        s2.append({**stage2.default_config(), "power_w": float(rng.uniform(10, 100)), "frequency_khz": float(rng.uniform(5, 10)),
                   "width_us": float(rng.uniform(2, 40)), "o2_flow_sccm": float(rng.uniform(100, 300)),
                   "water_temperature_c": float(rng.uniform(5, 60)), "water_volume_ml": float(rng.uniform(50, 5000)),
                   "water_ph": float(rng.uniform(2, 12)), "gap_mm": float((1, 2, 3)[int(rng.integers(3))]),
                   "bubble_gas": gases[int(rng.integers(2))], "treatment_time_min": 1.0})
    stage2_times = [timed(lambda c=c: stage2.summarise(stage2.run(c)))[0] for c in s2]
    out["PER-5"] = {"runs": len(stage2_times), "times_s": stage2_times, "max_s": max(stage2_times), "pass": max(stage2_times) <= 10.0}

    out["PER-6"] = per6()
    out["PER-7"] = per7()
    out["PER-8"], out["SEC-1"] = per8_and_sec1()
    out["PER-9"] = per9(results)
    out["PER-10"] = per10()
    return out


def per6() -> dict[str, Any]:
    """Screen reruns after an input change (AppTest), and the validator alone."""
    from streamlit.testing.v1 import AppTest

    from plasma_twin.services import stage1, stage2
    os.environ["PLASMA_TWIN_DB"] = str(Path(tempfile.mkdtemp()) / "per6.db")
    sys.path.insert(0, str(ROOT / "app"))
    result: dict[str, Any] = {}
    for page, label, values in (("pages/1_Chamber_configuration.py", "RF power P (W)", [20, 150, 50, 5, 75, 100, 300, 10, 60, 50]),
                                ("pages/8_Underwater_configuration.py", "Pulse width (µs)", [20, 150, 10, 5, 99, 40, 120, 2, 60, 10])):
        at = AppTest.from_file(str(ROOT / "app" / page), default_timeout=120)
        at.run()
        times = []
        for value in values:
            box = next(n for n in at.number_input if n.label == label)
            box.set_value(float(value))
            seconds, _ = timed(at.run)
            times.append(seconds)
        result[page] = {"field": label, "times_s": times, "max_s": max(times), "median_s": float(np.median(times)),
                        "exceptions": [str(e.value) for e in at.exception]}
    v1 = timed(lambda: [stage1.validate_config(stage1.default_config()) for _ in range(1000)])[0] / 1000
    v2 = timed(lambda: [stage2.validate_config(stage2.default_config()) for _ in range(1000)])[0] / 1000
    worst = max(r["max_s"] for r in result.values())
    return {**result, "validator_stage1_s": v1, "validator_stage2_s": v2, "max_s": worst, "pass": worst <= 0.5}


def per7() -> dict[str, Any]:
    from plasma_twin.data_io.importers import mapped, parse
    from plasma_twin.services.stage1 import downsample_peaks
    rng = np.random.default_rng(SEED)
    target = 50 * 1024 * 1024 - 1024  # just under the 50 MB limit
    out = {}
    for kind, name, sep in (("oes", "big.txt", "\t"), ("probe", "big.csv", ",")):
        rows = target // 20  # more lines than needed; the text is cut to just under 50 MB
        x = np.linspace(200, 1000, rows) if kind == "oes" else np.linspace(-100, 100, rows)
        y = rng.random(rows) * 1000
        raw = "\n".join(f"{a:.6f}{sep}{b:.6f}" for a, b in zip(x, y)).encode("ascii")[:target]
        raw = raw[:raw.rfind(b"\n")]
        started = time.perf_counter()
        parsed = parse(name, raw, kind)
        xs, ys = mapped(parsed, 0, 1, "A")
        downsample_peaks(xs, ys)
        seconds = time.perf_counter() - started
        out[kind] = {"megabytes": len(raw) / 1024 / 1024, "rows": parsed.rows, "seconds": seconds}
    worst = max(v["seconds"] for v in out.values())
    return {**out, "max_s": worst, "pass": worst <= 15.0}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def per8_and_sec1() -> tuple[dict[str, Any], dict[str, Any]]:
    port = free_port()
    command = [PYTHON, "-m", "streamlit", "run", "app/Home.py", "--server.port", str(port), "--server.headless", "true"]
    started = time.perf_counter()
    server = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    health_s, listeners = None, []
    try:
        while time.perf_counter() - started < 60:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=1) as response:
                    if response.status == 200:
                        health_s = time.perf_counter() - started
                        break
            except OSError:
                time.sleep(0.1)
        found = subprocess.run(["powershell", "-NoProfile", "-Command",
                                f"Get-NetTCPConnection -LocalPort {port} -State Listen | Select-Object -ExpandProperty LocalAddress"],
                               capture_output=True, text=True, timeout=60)
        listeners = sorted(set(found.stdout.split()))
    finally:
        server.kill()
        server.wait(timeout=30)
    script = ("import sys, time; sys.path.insert(0, 'app'); from streamlit.testing.v1 import AppTest; "
              "at = AppTest.from_file('app/Home.py', default_timeout=120); at.run(); "
              "print('exceptions', len(at.exception))")
    started = time.perf_counter()
    home = subprocess.run([PYTHON, "-c", script], cwd=ROOT, capture_output=True, text=True, timeout=300)
    home_s = time.perf_counter() - started
    per8 = {"server_to_health_s": health_s, "fresh_process_to_home_drawn_s": home_s, "home_output": home.stdout.strip(),
            "total_s": (health_s or 99) + home_s, "pass": health_s is not None and health_s + home_s <= 15.0}
    sec1 = {"port": port, "listening_addresses": listeners,
            "pass": bool(listeners) and all(a in ("127.0.0.1", "::1") for a in listeners)}
    return per8, sec1


def sec1() -> dict[str, Any]:
    """SEC-1 on its own (run 2's query inside per8_and_sec1 returned nothing): start the app, read its listeners two ways."""
    port = free_port()
    server = subprocess.Popen([PYTHON, "-m", "streamlit", "run", "app/Home.py", "--server.port", str(port), "--server.headless", "true"],
                              cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        started = time.perf_counter()
        while time.perf_counter() - started < 60:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=1):
                    break
            except OSError:
                time.sleep(0.2)
        query = subprocess.run(["powershell", "-NoProfile", "-Command",
                                f"Get-NetTCPConnection -LocalPort {port} -State Listen | ForEach-Object {{ $_.LocalAddress }}"],
                               capture_output=True, text=True, timeout=120)
        netstat = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=60)
        netstat6 = subprocess.run(["netstat", "-ano", "-p", "TCPv6"], capture_output=True, text=True, timeout=60)
    finally:
        server.kill()
        server.wait(timeout=30)
    from_query = sorted(set(query.stdout.split()))
    from_netstat = sorted({line.split()[1].rsplit(":", 1)[0] for line in (netstat.stdout + netstat6.stdout).splitlines()
                           if "LISTENING" in line and line.split()[1].endswith(f":{port}")})
    addresses = sorted(set(from_query) | set(from_netstat))
    loopback = ("127.0.0.1", "::1", "[::1]")
    return {"port": port, "get_nettcpconnection": from_query, "get_nettcpconnection_errors": query.stderr.strip()[:300],
            "netstat": from_netstat, "pass": bool(addresses) and all(a in loopback for a in addresses)}


def per9(results: list[Any]) -> dict[str, Any]:
    from plasma_twin.ai import inference
    from plasma_twin.ai.registry import Registry
    from plasma_twin.oes.spectrum import SpectrometerSettings, spectrum_for
    cards = [c for c in inference.current_models() if c.algorithm == "xgboost"]
    if not cards:
        return {"note": "no current Phase 10 XGBoost model on this computer", "pass": None}
    spectra = [spectrum_for(r, SpectrometerSettings.defaults(seed=k)) for k, r in enumerate(results[:20])]
    started = time.perf_counter()
    model, _ = Registry().load(cards[0].model_id)
    inference.estimate(spectra[0], model)
    first = time.perf_counter() - started
    later = [timed(lambda s=s: inference.estimate(s, model))[0] for s in spectra[1:]]
    return {"model": cards[0].model_id, "first_call_with_loading_s": first, "later_calls": len(later),
            "max_later_s": max(later), "median_later_s": float(np.median(later)), "pass": max(later) <= 1.0}


def per10() -> dict[str, Any]:
    from plasma_twin.ai import recommend as rc
    from plasma_twin.services import stage1, stage2
    try:
        models = {s: rc.load_surrogate(s) for s in (1, 2)}
    except ValueError as problem:
        return {"note": str(problem), "pass": None}
    goals = [rc.Goal("ne_target", 2e16), rc.Goal("tgas_target", 303.5), rc.Goal("line_max", line="line_750.387"),
             rc.Goal("lr_least_energy", 3.0), rc.Goal("lr_budget", budget_kj_l=1.0)]
    rows = []
    for goal in goals:
        messages: list[str] = []
        config = stage1.default_config() if goal.stage == 1 else stage2.default_config()
        seconds, found = timed(lambda g=goal, c=config: rc.recommend(g, models[g.stage][0], c, model_id=models[g.stage][1],
                                                                    progress=messages.append))
        rows.append({"objective": goal.objective, "seconds": seconds, "progress_messages": len(messages),
                     "twin_verified": all(c.twin for c in found.candidates), "reachable": found.reachable})
    worst = max(r["seconds"] for r in rows)
    return {"runs": rows, "max_s": worst, "pass": worst <= 60.0 and all(r["progress_messages"] >= 3 for r in rows)}


# ------------------------------------------------------------------------------------ REL-1 and ACC-3
def _grid_run(config: dict[str, Any]) -> dict[str, Any]:
    from plasma_twin.services import stage1
    try:
        result = stage1.run(config)
    except Exception as problem:  # noqa: BLE001 - every failure is a REL-1 finding
        return {"converged": False, "error": f"{type(problem).__name__}: {problem}"}
    worst = max(result.residuals.values())
    heating = sum(result.shares_percent("heating").values())
    losses = sum(result.shares_percent("losses").values())
    return {"converged": worst < 1e-8, "worst_residual": worst, "heating_sum_percent": heating, "loss_sum_percent": losses}


def rel1() -> dict[str, Any]:
    from plasma_twin.services import stage1
    grid = [{**stage1.default_config(), "mixture": m, "rf_power_w": float(p), "pressure_mbar": float(q), "ar_flow_sccm": float(f),
             "eedf": e, "n2_percent": 5.0, "o2_percent": 5.0}
            for m in stage1.MIXTURES for p in np.linspace(10, 100, 5) for q in np.linspace(0.1, 0.5, 5)
            for f in np.linspace(100, 500, 5) for e in ("Druyvesteyn", "Maxwellian")]
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(_grid_run, grid, chunksize=8))
    converged = [r for r in rows if r["converged"]]
    failures = [{**{k: g[k] for k in ("mixture", "rf_power_w", "pressure_mbar", "ar_flow_sccm", "eedf")}, **r}
                for g, r in zip(grid, rows) if not r["converged"]]
    shares_ok = [r for r in converged if abs(r["heating_sum_percent"] - 100) <= 0.5 and abs(r["loss_sum_percent"] - 100) <= 0.5]
    return {"REL-1": {"configurations": len(grid), "converged": len(converged), "failures": failures[:20],
                      "seconds": time.perf_counter() - started, "pass": len(converged) == len(grid)},
            "ACC-3": {"runs_checked": len(converged), "shares_within_0_5_percent": len(shares_ok),
                      "worst_residual": max((r["worst_residual"] for r in converged), default=None),
                      "worst_heating_sum_percent": max((abs(r["heating_sum_percent"] - 100) for r in converged), default=None),
                      "worst_loss_sum_percent": max((abs(r["loss_sum_percent"] - 100) for r in converged), default=None),
                      "pass": len(shares_ok) == len(converged) == len(grid)}}


# ------------------------------------------------------------------------------------ REL-3
CHILD = """
import sys, time
sys.path.insert(0, {root!r})
from pathlib import Path
from plasma_twin.storage.sessions import SessionStore
store = SessionStore(Path({db!r}))
print("ready", flush=True)
k = 0
while True:
    k += 1
    sid = store.save(1, {{"rf_power_w": 50.0, "k": k}}, f"hash{{k}}", {{"te_ev": 3.0, "values": list(range(200))}}, "crash test", "0.13.0")
    print(sid, flush=True)
"""


def rel3(kills: int = 50) -> dict[str, Any]:
    import sqlite3
    import threading

    from plasma_twin.storage.sessions import SessionStore
    folder = Path(tempfile.mkdtemp())
    db = folder / "crash.db"
    rng = np.random.default_rng(SEED)
    lost, corrupt, committed_total = [], 0, 0
    for k in range(kills):
        child = subprocess.Popen([PYTHON, "-c", CHILD.format(root=str(ROOT), db=str(db))], stdout=subprocess.PIPE, text=True)
        reported: list[str] = []
        ready = threading.Event()

        def read(pipe=child.stdout, out=reported, flag=ready):
            for line in pipe:
                line = line.strip()
                if line == "ready":
                    flag.set()
                elif line.startswith("S-"):
                    out.append(line)

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        ready.wait(timeout=60)
        time.sleep(float(rng.uniform(0.05, 1.0)))
        child.kill()  # forced termination, mid-save or between saves
        child.wait(timeout=30)
        reader.join(timeout=10)
        committed_total += len(reported)
        conn = sqlite3.connect(db)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                corrupt += 1
        finally:
            conn.close()
        stored = {r.session_id for r in SessionStore(db).list(limit=None)} if reported else set()
        lost += [sid for sid in reported if sid not in stored]
    return {"kills": kills, "sessions_reported_committed": committed_total, "lost": len(lost), "corrupt_checks": corrupt,
            "pass": not lost and corrupt == 0}


# ------------------------------------------------------------------------------------ REL-4
def _numbers(value: Any, prefix: str = "") -> dict[str, float]:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            out.update(_numbers(v, f"{prefix}.{k}"))
        return out
    if isinstance(value, (list, tuple, np.ndarray)):
        out = {}
        for k, v in enumerate(np.asarray(value, dtype=object).ravel().tolist() if isinstance(value, np.ndarray) else value):
            out.update(_numbers(v, f"{prefix}[{k}]"))
        return out
    if isinstance(value, (int, float, np.floating, np.integer)) and not isinstance(value, bool):
        return {prefix: float(value)}
    return {}


def rel4() -> dict[str, Any]:
    from plasma_twin.services import stage1
    worst, compared = 0.0, 0
    for config in stage1_draws(10):
        a, b = _numbers(stage1.run(config).as_dict()), _numbers(stage1.run(config).as_dict())
        for key, x in a.items():
            y = b[key]
            compared += 1
            if x != y:
                worst = max(worst, abs(x - y) / max(abs(x), abs(y)))
    return {"configurations": 10, "numbers_compared": compared, "largest_relative_difference": worst, "pass": worst < 1e-9}


def per4() -> dict[str, Any]:
    """Phase 15: the PER-4 sweep again, timing the gaps between the progress updates M3 now shows."""
    from plasma_twin.services import stage1
    from plasma_twin.stage1.sweep import sweep
    stage1.run(stage1.default_config())  # imports and rate tables, as in PER-1
    stamps: list[float] = []
    started = time.perf_counter()
    points = sweep(stage1.to_inputs(stage1.default_config()), "rf_power_w", np.linspace(10, 100, 200),
                   progress=lambda done, total: stamps.append(time.perf_counter()))
    total = time.perf_counter() - started
    gaps = np.diff([started] + stamps)
    return {"points": len(points), "solved": sum(p.solved for p in points), "progress_updates": len(stamps),
            "total_s": total, "longest_gap_between_updates_s": float(gaps.max()), "median_gap_s": float(np.median(gaps)),
            "pass": total <= 120.0 and float(gaps.max()) <= 2.0, "measured_in": "Phase 15"}


PARTS = {"per": per, "rel1": rel1, "rel3": rel3, "rel4": rel4, "sec1": sec1, "per4": per4}
KEYS = {"rel3": "REL-3", "rel4": "REL-4", "sec1": "SEC-1", "per4": "PER-4 (Phase 15)"}


def main() -> None:
    wanted = sys.argv[1:] or list(PARTS)
    if len(wanted) > 1:  # run 2 lesson: AppTest (PER-6) replaces __main__, which breaks REL-1's process pool, so one part per process
        for name in wanted:
            subprocess.run([PYTHON, __file__, name], cwd=ROOT, check=False)
        return
    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    data["machine"] = {"processor": platform.processor(), "system": f"{platform.system()} {platform.release()} {platform.version()}",
                       "python": platform.python_version(), "logical_cpus": os.cpu_count()}
    for name in wanted:
        print(f"--- {name}", flush=True)
        started = time.perf_counter()
        result = PARTS[name]()
        result = result if name in ("per", "rel1") else {KEYS[name]: result}
        data.update(result)
        data.setdefault("measured_at", {})[name] = time.strftime("%Y-%m-%d %H:%M:%S")
        print(json.dumps(result, indent=1, default=float)[:4000], flush=True)
        print(f"({time.perf_counter() - started:.0f} s)", flush=True)
        OUT.write_text(json.dumps(data, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
