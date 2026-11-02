# Building Journey

This file tells the story of how the project was built, phase by phase: what was made, which techniques were used and why, what went wrong, and how each problem was handled. A new section is added at the end of every phase.

It is written so that either of us can explain any decision to the evaluation committee without notes. Technical detail lives in the code, `BUILD_STEPS.md` and `docs/`; this file explains the reasoning.

**Golden rules we followed throughout**
- Build one phase, test it, pass its exit gate, commit, then move on.
- Never invent a number. Every physical value comes from a source we read, and its citation is recorded.
- Fix the rules of a comparison before running it, and never change the model to make a comparison pass. A failed result is recorded as it is.
- Report failures honestly, with their likely causes.

---

## Before Phase 0: requirements and planning

**What we made**
- Scope Document v3.1 and SRS v1.1 (`docs/scope/`, `docs/srs/`). The SRS has 28 use cases, 16 screen mockups, 149 functional requirements and 38 non-functional requirements.
- `BUILD_STEPS.md`: the build plan, phases 0–14, each with tests and an exit gate.
- An SRS presentation and a viva preparation guide (`docs/presentation/`, kept out of git for now).

**Decisions and why**
- **A new repository.** The supervisor redirected the project in October 2026 (three stages: low-pressure argon plasma with OES, underwater oxygen plasma, Langmuir probe). The old project stays untouched, and the new one lives in `virtual-plasma-lab`.
- **Two core modules.** Digital Twin (all the physics) and AI. AI was "optional" in the supervisor's answers, but the team made it core.
- **The supervisor's answers are authoritative.** Where he left something blank, we used published literature and labelled it as such (`docs/UNDERSTANDING.md`).

**Problems and how we handled them**
- **Word hung while exporting PDF.** Fixed by saving a copy with `SaveAs2` instead of `ExportAsFixedFormat`.
- **A blank page after the table of contents.** Fixed by shrinking the TOC's closing paragraph.
- **Plagiarism report.** We could not run Turnitin ourselves, so a clearly marked placeholder page was added instead of a fake report.

---

## Phase 0: project skeleton

**What we made**
- **Folder layout:** a Python virtual environment and the folder plan from `BUILD_STEPS.md`.
- **`envelope.toml`:** every allowed range, default and tolerance, in one file.
- **SQLite database schema:** with a version number.
- **Basics:** a minimal Streamlit home page, pytest, and GitHub Actions to run the tests on every push.

**Techniques and why**
- **One configuration file (TOML, read with Python's built-in `tomllib`).** The screens and the physics both read it, so a screen can never offer a value the physics refuses. Because it is tracked in git, nobody can quietly widen the ±30 % tolerance after seeing a result.
- **Exact versions in `requirements.txt`**, so results can be reproduced.

**Problems and how we handled them**
- **The plan's own test was wrong.** It required min < default < max, but the supervisor's values put a default on a limit (10 kV is both). Corrected to min ≤ default ≤ max.
- **Wrong count in the plan.** I had counted 23 ranges; there are 22.
- **GitHub refused the push.** The login lacked the `workflow` permission. Fixed by logging in again with that permission.
- **Claude was listed as a contributor on GitHub.** Both commits were rewritten without that credit and pushed again. Rule since then: no Claude credit in any commit.
- **The preview tool kept opening the old project.** Worked around by starting Streamlit directly from the new folder.

---

## Phase 1: reference data

**What we made**
- **Loaders** for NIST atomic lines (Ar I, O I, H I), LXCat electron cross-sections (Ar, N₂, O₂), N₂ and OH molecular constants, and benchmark values.
- **`manifest.json`:** each data file with its source, citation, date and SHA-256 checksum.
- **`scripts/fetch_reference.py`:** downloads the NIST data and registers the LXCat file.

**Techniques and why**
- **Checksums.** Every result depends on these numbers. A half-downloaded or edited file would give wrong physics that looks right, so the loaders refuse any file whose checksum does not match (event E6).
- **Some data stays out of the public repository.** LXCat does not allow redistribution, and NIST holds copyright in its compilation. The repo keeps only citations and checksums, and each person downloads the data.
- **An honest program name when downloading from NIST**, instead of pretending to be a browser.

**Problems and how we handled them**
- **NIST blocked Python's default identifier.** Fixed by naming our tool honestly.
- **I misremembered two NIST values** (4.45 and 3.31 instead of 4.5 and 3.3). Checked against the downloaded rows and corrected the tests.
- **LXCat needs a personal agreement and a human check.** You read the terms and agreed. I then selected the Biagi database (Ar, N₂, O₂, all 107 processes) in Chrome. The Next button was slow and Chrome stopped screenshots while minimized; it worked once Chrome was in front.
- **The LXCat file reader had only been tested on a fake file.** It worked on the real file unchanged. Its real layout taught us one thing: the O₂ three-body attachment cross-section is "normalized to gas density", so it is not a normal area. The reader now keeps each process's comments so the physics code cannot miss this.
- **No benchmark values could be read at first** (paywalls and human checks). We refused to use numbers from search summaries. By team decision the item moved to Phase 2's gate.

---

## Phase 2: argon physics model (in progress, exit gate not passed)

**What we made**
- **2a, electron energy distribution (`eedf.py`):** Maxwellian and Druyvesteyn shapes in one family, both with mean energy (3/2)·T_e.
- **2b, rate coefficients (`rates.py`):** integrated from the real Biagi cross-sections, tabulated once per shape for speed. It also computes the wall quantities (Bohm speed, floating potential, energy carried to walls) from the distribution itself.
- **2c, global model (`global_model.py`):** a 0D model of a 13.56 MHz argon CCP, using Lieberman's high-pressure capacitive model. It includes a collisional sheath, bulk and sheath ohmic heating, and stochastic heating.
- **2d, excited atoms (`argon_kinetics.py`):** metastable, resonant and 4p argon atoms, two-step ionization, and losses to the walls.
- **Validation:** `benchmark.py` compares the model with published measurements, and `docs/validation/` holds the record.
- **`SUPERVISOR_QUESTIONS.md`:** 18 questions, each with the default we use until he answers.

**Techniques and why**
- **Benchmarks recorded before any model existed.** Values come from Saikia et al., *AIP Advances* 8, 045113 (2018), open access, argon at 13.56 MHz and 100–400 mTorr. They were committed first, so nobody can say they were chosen to fit.
- **Lieberman's 2015 course model.** At 0.1–0.5 mbar an ion's mean free path is about 0.1 mm, much shorter than the sheath, so the usual low-pressure textbook sheath does not apply. I read the formulas from his slides as images, and a test reproduces his own worked example (1.2 W, 6.3 W, 0.33 cm).
- **Edge factors with length 2·s_m.** Particle-in-cell simulations (Lafleur & Chabert 2014) show that in a CCP at these pressures, ions are lost faster than the textbook formula says. Lieberman's correction was used, and the textbook form is kept as an option.
- **Root finding.** `brentq` for one unknown at a time. Once excited atoms tie T_e to n_e, Powell's hybrid method (`scipy.optimize.root`) solves all seven balances together, started from the simpler solution.
- **Exact checks of the maths.** Integrals are tested against cases with known answers: a constant cross-section, a step at threshold, and the Maxwellian wall values.
- **Pre-registered comparisons.** The rules (points, settings, geometry, pass mark) were written into `BUILD_STEPS.md` and committed before each run.

**Problems and how we handled them**
- **Screening temperature slightly wrong (1.0085 instead of 1).** The integral has a 1/√ε spike at zero energy that a grid cannot resolve. Replaced by the exact formula.
- **Ionization rate 40 % above the published fit at 3 eV.** Two independent integrations agreed, so the code was right. The fit uses 17.44 eV where argon ionizes at 15.76 eV, and the gap shrinks steadily with T_e (1 % at 10 eV). The test was changed openly, with the reason in `BUILD_STEPS.md`.
- **The plan's tests assumed the simple model.** With real sheaths, n_e grows as about P^0.66, not ∝ P, and T_e moves slightly with power. The tests were updated, with reasons.
- **A test's own integral was too coarse at low T_e.** Replaced by adaptive quadrature.
- **High RF voltage (about 1.8 kV at 50 W).** Probably because secondary-electron (γ-mode) heating is not in the model. Recorded as a known limitation.
- **Benchmark run 1 failed.** n_e was 161–217 % high and T_e 117–137 % high. The measured T_e was too low for ground-state ionization alone, which pointed to two-step ionization through metastables.
- **Benchmark run 2, with metastables, also failed** (n_e +159–216 %, T_e +115–136 %). Two-step ionization makes only 5–11 % of the ions, so metastables are ruled out as the main cause. We also noted openly that a test run had shown the gate still failing before the record was written. The model was not changed after that.
- **Benchmark run 3: comparing T_e the way the probe measured it.**
  - We read the paper's method first: T_e "is derived from the linear part of the logarithmic electron current". That is a slope, not the mean energy.
  - We built `probe/retardation.py`, the first piece of the virtual Langmuir probe. It computes the electron current a probe collects from the model's own EEDF, and fits the slope the same way. For a Maxwellian it returns exactly T_e, which the tests check.
  - The fit window (plasma potential to floating potential) was fixed and committed before any code. The code was committed before the run. This time the test suite ran without the benchmark file, so the result stayed unseen until the run.
  - Result: T_e dropped from about +125 % to +54–69 % off, so the definition explains about half of the T_e gap. n_e is unchanged at +159–216 %, and the gate still fails.
- **One honest note on run 3.** For a fixed EEDF shape, the probe reading is a fixed fraction of T_e (0.713 for Druyvesteyn). That number appeared while testing the code, so the T_e outcome could be worked out before the run. Nothing was changed because of it, and the record says so.
- **What remains:**
  - The paper does not state its fit window. Fitted near the floating potential, the same model reads within about 30–40 %. We report this for information but do not use it, because the window was fixed beforehand.
  - n_e is now the main gap. The likely causes are generator versus absorbed power (supervisor question Q3), the asymmetric electrodes, and the missing γ-mode heating.

**Where it stands:** the model is built and well tested (147 tests pass), and the trends match the measurements. The ±30 % gate is not met. All three runs are recorded in `docs/validation/phase2_stage1_benchmarks.md`.
