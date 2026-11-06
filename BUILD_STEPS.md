# Build Steps — Plasma Digital Twin (new project)

This file is the build plan. We build **one phase at a time**:

1. Build only what that phase lists.
2. Run the phase's tests. All of them must pass.
3. Check the phase's **exit gate**: every box ticked.
4. Add the phase's section to `BUILDING_JOURNEY.md`: what was built, the techniques used and why, what failed, and how it was handled.
5. Commit, with the phase named in the message.
6. Only then start the next phase.

If a test fails, fix it in the same phase. Never carry a broken phase forward.

Requirement IDs (FR, PER, REL, ACC, AIQ and so on) refer to `docs/srs/SRS_Plasma_Digital_Twin_v1.1.docx`. Module numbers refer to `docs/scope/Scope_Document_v3.1.docx`. Stage 1 comes first because the supervisor ranks it most important.

---

## The two core modules

The project has **two core modules**. Both are mandatory and are equally important to the final product:

| Core module | What it is | Phases |
|---|---|---|
| **Core Module 1 — Digital Twin (physics engine)** | All the physics: Stage 1 low-pressure argon plasma, virtual OES, virtual Langmuir probe (Stage 3), Stage 2 underwater disinfection plasma, validation against published and measured data | 1–5, 7, 8 |
| **Core Module 2 — AI Module** | Learns from the twin: spectrum → plasma parameters, physics-relationship anomaly detection, fast surrogate with SHAP explanations, counterfactual recommendations (inverse design), and the training / evaluation / registry framework behind them | 9–13 |

Supporting parts (dashboard screens, sessions, import and export) are built alongside them in Phases 0, 6 and 8.

The twin is built first because the AI module learns from data the twin generates. AI models are trained **only** on synthetic data from the twin; measured laboratory data are used only to test and validate, never to train.

---

## Overview

| Phase | Core module | What we build | Who leads | Depends on |
|---|---|---|---|---|
| 0 | Set-up | Project skeleton, environment, config, database, tests set-up | Both | — |
| 1 | Twin | Reference data (NIST lines, LXCat cross-sections, benchmarks) | Rayyan | 0 |
| 2 | Twin | Stage 1 core physics: EEDF, rate coefficients, global model (argon only) | Rayyan | 1 |
| 3 | Twin | Stage 1 extensions: gas flow, gas temperature, N₂/O₂ mixtures, 1D profile, sweeps | Rayyan | 2 |
| 4 | Twin | Virtual OES: CR model, spectrum, Boltzmann plot, gas temperature | Rayyan | 3 |
| 5 | Twin | Virtual Langmuir probe and diagnostics comparison | Rayyan | 3 |
| 6 | Supporting | Stage 1 dashboard screens and sessions (M1–M7, M11 basic) | Sadeem | 2–5 |
| 7 | Twin | Stage 2 underwater twin, Hom model, underwater OES, screens M8–M9 | Rayyan + Sadeem | 1, 4 |
| 8 | Twin + supporting | Measured-data import, validation, export (M10, M11 export) | Sadeem | 6, 7 |
| 9 | AI | Dataset generation, training / evaluation framework, model registry (M16) | Rayyan | 4, 5, 7 |
| 10 | AI | Spectrum → plasma parameter inference (M12) | Rayyan | 9 |
| 11 | AI | Surrogate model of the twin with SHAP explanations (M15) | Rayyan + Sadeem | 9 |
| 12 | AI | Physics-relationship anomaly detection (M13) | Rayyan | 9 |
| 13 | AI | Counterfactual recommendations / inverse design (M14) | Rayyan + Sadeem | 11 |
| 14 | Both | Full test pass, NFR and AI-quality checks, final report | Both | all |

- Phases 4 and 5 both need only Phase 3, so they can be built in parallel.
- Phases 10, 11 and 12 all need only Phase 9, so they can also run in parallel.
- Sadeem can lay out the screens with placeholder data before the logic behind them is ready.

---

## Planned folder layout

```
plasma-digital-twin-v2/
├── app/                      # Streamlit pages (UI only, no physics, no model training)
│   ├── Home.py               # M1
│   └── pages/                # M2 … M16, one file per screen
├── plasma_twin/              # all logic (no Streamlit imports here)
│   ├── config/envelope.toml  # every allowed range, default and tolerance (±30 %)
│   │
│   │   # ---- Core Module 1: Digital Twin ----
│   ├── reference/            # loaders for NIST, LXCat, benchmark data
│   ├── stage1/               # eedf, rates, global_model, gas_temperature, mixtures, profile1d, sweep
│   ├── oes/                  # cr_model, spectrum, boltzmann, gas_temp, line_ratio
│   ├── probe/                # iv_model, analysis, eepf
│   ├── compare/              # diagnostics comparison
│   ├── stage2/               # pulse, bubble_model, liquid, hom, uw_oes
│   │
│   │   # ---- Core Module 2: AI ----
│   ├── ai/
│   │   ├── datasets.py       # twin-generated training data, faults, pre-registered noise, seeds
│   │   ├── registry.py       # MLflow logging, model cards, twin-version check
│   │   ├── inference.py      # spectrum -> Te, ne, Tgas with conformal intervals
│   │   ├── surrogate.py      # fast twin surrogate + SHAP
│   │   ├── anomaly.py        # Isolation Forest on physics residuals
│   │   └── recommend.py      # inverse design: search on surrogate, verify with twin
│   │
│   │   # ---- Supporting ----
│   ├── data_io/              # importers, validation, export
│   └── storage/              # SQLite db and sessions
├── models/                   # trained AI models + model cards (versioned with the twin)
├── data/reference/           # NIST/LXCat/benchmark files + manifest with checksums and citations
├── tests/                    # one test file per module: test_<module>.py
├── docs/                     # scope, SRS, supervisor questionnaires, notes
├── requirements.txt          # exact versions from pip freeze
└── BUILD_STEPS.md            # this file
```

Rules:
- `plasma_twin/` never imports Streamlit. The UI calls the logic, and the logic never knows the UI exists.
- The AI code calls the twin, but the twin never imports the AI code. So the physics can always be tested and defended without the AI.

---

## Phase 0 — Project skeleton and set-up

**Goal:** an empty but working project in which tests run and the configuration and database load.

**Build**
- Python 3.12+ virtual environment (`.venv`). Install Streamlit, Plotly, NumPy, SciPy, pandas and pytest, then pin the exact versions with `pip freeze > requirements.txt`.
- The folder layout above, with an empty `__init__.py` in each package.
- `plasma_twin/config/envelope.toml`: every range, default and the ±30 % tolerance from the SRS (Appendix C). Read it with Python's built-in `tomllib`, so no new dependency is needed. It is the single source of ranges for both the UI and the validator.
- `plasma_twin/storage/db.py`: the SQLite schema (sessions, configurations, results, imported files, validation results) with a version number.
- A minimal `app/Home.py` that opens and shows "Plasma Digital Twin".
- Optional: a GitHub Actions workflow that runs pytest on every push.

**Tests** (`tests/test_config.py`, `tests/test_db.py`)
- The config loads, and every range has min < max and min ≤ default ≤ max. A default may equal a limit because the supervisor's values do (10 kV is both the default and the maximum).
- The database is created in a temporary folder and all tables exist; creating it a second time does not fail.

**Exit gate**
- [x] `pytest` passes.
- [x] `streamlit run app/Home.py` opens in the browser.
- [x] `requirements.txt` has exact versions.

**Commit:** `Phase 0: project skeleton, config, SQLite schema, pytest`

---

## Phase 1 — Reference data

**Goal:** all published data the models need, stored locally with a citation and a checksum (MNT-2, CON-9, E1/E6).

**Build**
- `data/reference/`, described in its `README.md`. NIST and LXCat files stay out of the public repository, because of their copyright and redistribution terms. `scripts/fetch_reference.py` downloads the NIST files. Each team member downloads the LXCat file personally, because LXCat requires agreement to its policy and uses a human-verification check.
  - NIST argon line data (wavelength, A_ki, g_k, E_k for the Ar I 2p→1s lines and the 3p lines used).
  - O I, H-alpha and OH data for Stage 2.
  - LXCat argon cross-sections (elastic, excitation, ionization), with N₂ and O₂ sets.
  - N₂ C–B band constants.
  - Published benchmark values for validation. Each value must be read in its source and recorded with where it was found.
- `data/reference/manifest.json`: for each file, its source, citation, download date and SHA-256 checksum.
- `plasma_twin/reference/loaders.py`: functions that read each file into NumPy arrays with stated units and verify the checksum.

**Tests** (`tests/test_reference.py`)
- Every file in the manifest exists and its checksum matches.
- Spot values are correct, for example that Ar I 811.53 nm has the NIST A value.
- A corrupted file is detected and refused, and an absent file is reported as missing (event E6).
- Spot-value tests skip where the downloaded files are absent, as on GitHub. Run them locally.

**Exit gate**
- [x] Every value has a citation in the manifest. (LXCat: Biagi database, MAGBOLTZ 8.97, retrieved 2 November 2026.)
- [x] Tests pass with no skips on a computer that has all the data. (48 passed, 0 skipped, 2 November 2026.)
- [x] At least three Stage 1 benchmark points are recorded, or moved to Phase 2's gate by decision. **Moved to Phase 2's gate by team decision, 2 November 2026:** nothing is compared with benchmarks until the Phase 2 model exists.

**Commit:** `Phase 1: reference data with manifest, checksums and loaders`

---

## Phase 2 — Stage 1 core physics (argon only)

**Goal:** the heart of the project, the 0D global model of a 13.56 MHz argon CCP (Module 2; FR13.2, CON-2). It is built in three small steps, each tested before the next.

**2a — EEDF** (`stage1/eedf.py`)
- Maxwellian and Druyvesteyn distributions, both normalised to the same mean energy.
- Tests:
  - Each distribution integrates to 1.
  - The mean energy is (3/2)·T_e.
  - The Druyvesteyn tail is lower than the Maxwellian tail at high energy.

**2b — Rate coefficients** (`stage1/rates.py`)
- K(T_e) = ∫ σ(ε)·v(ε)·f(ε) dε, using the LXCat cross-sections and the chosen EEDF.
- Tests:
  - K_iz rises steeply with T_e.
  - The Maxwellian K_iz at 3 eV is close to the published value within the stated band. **Changed, 2 November 2026:** it is 40 % above the published fit (Kemaneci et al. 2016) at 3 eV, but within ±30 % from 5 eV up, and the gap shrinks steadily as T_e rises. Two independent integrations agree, so the cause is the fit's form (it uses 17.44 eV where argon ionizes at 15.76 eV). The test now checks agreement at 5–10 eV and pins the low-T_e gap. The integration itself is tested against exact answers.
  - The Druyvesteyn K_iz is below the Maxwellian value.

**2c — Global model** (`stage1/global_model.py`)
- Particle balance K_iz(T_e)·n_g = u_B(T_e)/d_eff, solved for T_e with `scipy.optimize.brentq`.
- Power balance P_abs = e·n₀·u_B·A_eff·E_T(T_e), solved for n_e.
- Collisional sheath and edge-to-centre factors that are valid across 0.1–0.5 mbar. This range is 75–375 mTorr, much higher than the old project's 1–20 mTorr, so these forms must be chosen for it.
- Outputs: T_e, n_e, ion flux and the power-balance shares. Every output is computed from T_e and n_e and none is set by hand.
- As built: the high-pressure capacitive model of Lieberman's 2015 UC Berkeley short course (collisional Child law, bulk and sheath ohmic heating, stochastic heating). Edge factors use the effective length 2·s_m, following Lieberman and the PIC results of Lafleur & Chabert (2014). See the module docstring for every assumption.
- Tests:
  - T_e does not depend on power; n_e is proportional to power. **Changed, 2 November 2026:** with real sheaths, power changes the sheath width and so the bulk size. T_e may now move by less than 2 % over 10–100 W. Ion acceleration in the sheaths takes a growing share of power as the RF voltage rises, so n_e grows as about P^0.6–0.7; the test checks that n_e rises with a slope between 0.5 and 1.
  - The solver converges on a grid of at least 500 configurations across the envelope (REL-1).
  - The residual is below 10⁻⁸ and the power shares sum to 100 ± 0.5 % (ACC-3).
  - The same inputs give the same outputs (REL-4).
  - Out-of-range inputs are rejected (E3).

**Benchmark comparison rules** (written and committed before the first comparison, ACC-4)
- Points: Saikia et al. (2018), Table II, 50 W at 100, 200 and 300 mTorr. These are the three recorded points inside the 0.1–0.5 mbar envelope. The 400 mTorr and 73 mTorr points are outside it and are reported only for information.
- Model settings: the defaults, Druyvesteyn EEDF (supervisor) and `edge_length = "sheath"`. Gas at 300 K. The stated 50 W is taken as absorbed power.
- Geometry: their discharge is asymmetric (electrodes 8 and 10 cm across). Our model is symmetric, so it uses the mean radius, 4.5 cm, and their 7.5 cm gap.
- Compared: model centre density n_0 with measured n_e (the probe sits 30 mm from the electrode, near the centre of the 75 mm gap), and model T_e (2/3 of the mean energy) with measured T_e.
- Pass: every compared value within ±30 % (`envelope.toml`). Runs with the Maxwellian EEDF or `edge_length = "bulk"` are shown for information and cannot be used to pass.
- If a point fails, the result is reported as it is. Settings are not changed after seeing it.

**2d — Excited argon atoms and two-step ionization** (`stage1/argon_kinetics.py`; moved forward from Phase 3 by team decision, 2 November 2026)
- Why: the first comparison showed a measured T_e (1.0–1.4 eV) too low for ionization from the ground state alone, which points to two-step ionization through excited atoms. This is a stated physical cause, not a fit to the result.
- Fixed before any second comparison:
  - Three lumped excited levels: metastable 4s_m (Biagi 1s5 + 1s3), resonant 4s_r (1s4 + 1s2) and 4p (2p1–2p10). Excitation from the ground state is integrated from the Biagi data with the chosen EEDF. Higher levels count only as energy loss.
  - Processes from excited levels: Kemaneci et al., arXiv:1612.07268 (2016), Table III, rows 7–10 and 13–26 (the Gudmundsson argon set). Row 11 is left out: it has no reference and an impossible size for a collision between two atoms. Rows 12 and 27–33 are left out: charge exchange does not change the densities, and dimer ions and recombination are negligible at 10¹⁶ m⁻³. These rates are Maxwellian fits; using them with a Druyvesteyn EEDF is an approximation, stated in the code.
  - Wall loss of excited atoms: Chantry's formula with Λ₀⁻² = (π/l)² + (2.405/R)², every atom de-excited at the wall (γ = 1). Diffusion D₀ = 0.073 cm²/s at 273 K and 1 atm, scaling as (T/T₀)^1.92 / p (Zhakhovskii & Nishihara, arXiv:physics/0507076).
  - Excited states are on by default. `excited_states=False` keeps the ground-state-only model for comparison.
- Tests: switching excited states off reproduces the 2c results exactly. With them on, T_e is lower than without, it falls as power rises (more electrons, more two-step ionization), all balances close below 10⁻⁸, and the solver converges over the whole envelope.

**Second benchmark comparison rules** (fixed before the run)
- Same points, geometry, tolerance and pass rule as the first comparison. The only change is the model: the 2d excited states, on by default. The model is committed before the comparison is run.

**Third benchmark comparison rules: probe-style T_e** (fixed 2 November 2026, before any code or result)
- Why: Saikia et al. state that their T_e "is derived from the linear part of the logarithmic electron current", so they measure an inverse slope, not the mean energy. With a non-Maxwellian EEDF the two differ. Comparing like with like means asking what their method would read from the model's own EEDF.
- Probe-style T_e: the electron current a probe collects when held V below the plasma potential is I_e(V) ∝ ∫ v f(ε) (1 − V/ε) dε over ε > V. This holds for any convex probe with isotropic electrons (Druyvesteyn's result), so the probe's size and shape do not matter. Ion current is assumed perfectly subtracted.
- Window: a least-squares straight line through ln I_e against V, on an even voltage grid, from the plasma potential (V = 0) to the floating potential (V = V_f, the model's own floating potential for its EEDF). Probe-style T_e = −1 / slope. Our code is `plasma_twin/probe/retardation.py`, the first piece of the Phase 5 virtual probe.
- Compared: probe-style T_e with measured T_e; n_e is compared exactly as before. Same points, settings, geometry, tolerance and pass rule as runs 1 and 2. The half-windows (0 to V_f/2, V_f/2 to V_f) are shown for information only and cannot be used to pass.
- The code is committed before the comparison is run.

**Exit gate**
- [x] At least three Stage 1 argon benchmark points (0.1–0.5 mbar, 13.56 MHz) are in `data/reference/constants/benchmarks.csv`, each read in its source and recorded with its citation and location. They must be committed **before** the model is first compared with them (ACC-4). Moved here from Phase 1. (Commit e28c89e.)
- [x] 2a, 2b and 2c tests pass. (116 passed, 2 November 2026.)
- [x] One run takes ≤ 2 s (PER-1). (About 0.08 s; 0.5 s for the first run, which builds the rate tables.)
- [ ] T_e and n_e at 3 reference points are within ±30 % of published values (ACC-1). The tolerance is fixed in `envelope.toml` before this check is run. **Failed, 2 November 2026,** on run 1 (n_e +161 to +217 %, T_e +117 to +137 %), on run 2 with excited atoms (n_e +159 to +216 %, T_e +115 to +136 %), and on run 3 with probe-style T_e (n_e unchanged, T_e +54 to +69 %). Record and analysis: `docs/validation/phase2_stage1_benchmarks.md`.
  **Left open by team decision, 2 November 2026.** Phase 2 is closed with this one item unmet. The remaining n_e gap most likely needs the supervisor's answer to Q3 (generator power or absorbed power), and further physics changes without it would risk tuning the model to the data. When Q3 is answered, the comparison is re-run under the same rules and recorded as run 4.

**Phase 2 closed** on 2 November 2026: 145 tests pass, every other gate item is met, and the open item above is recorded.

**Commit:** `Phase 2: Stage 1 EEDF, rate coefficients and argon global model`

---

## Phase 3 — Stage 1 extensions

**Goal:** everything else the supervisor asked for in Stage 1 (Module 2, FE-2.3, FE-2.5, FE-2.6).

Built in five small steps, each tested and committed before the next. Every new effect has a switch, and with every switch off the Phase 2 results come back exactly (regression).

**3a — Gas flow** (`stage1/gas_flow.py`)
- Converts sccm to atoms per second at the standard conditions sccm is defined at (0 °C, 1 atm).
- Residence time τ = (gas atoms in the chamber) / (atoms fed per second), using the 40 × 40 cm chamber volume.
- Excited atoms are also lost by being pumped away: loss rate 1/τ, added to the wall loss.
- Expected from the numbers before building: in pure argon this is tiny (τ ≈ 1–5 s against wall losses of hundreds per second). Flow matters mainly in 3e, where it sets how much N₂ and O₂ enters. The test checks the effect is small, not that it is large.
- Tests: the unit conversion; τ scales as p / Q; flow 0 reproduces Phase 2 exactly.

**3b — Gas temperature** (`stage1/gas_temperature.py`)
- T_gas is now an output. The heat put into the gas equals the heat conducted to the walls.
- Heat into the gas: elastic electron–atom collisions (from the model's energy budget) plus the energy released when excited atoms are quenched in collisions with atoms. Ion energy gained in the sheaths is taken to reach the electrodes, carried by ions and fast neutrals, so it is not counted. This makes T_gas a lower estimate, and the code says so.
- Heat to the walls: exact solution of steady conduction in a cylinder (radius R, length l) with uniform heating and walls at 300 K, using a series of Bessel and cosine modes. Thermal conductivity κ(T) is from NIST (`argon_thermal_conductivity.csv`). The temperature jump at the walls is neglected; the gas mean free path is much smaller than the gap.
- T_gas sets the gas density (n_g = p / k T_gas), so the model is re-solved until T_gas stops changing.
- Tests: the conduction series matches the exact slab result L²/12 when R is large; T_gas rises with power and stays above the wall temperature; gas heating off reproduces Phase 2.

**3c — 1D axial profile** (`stage1/profile1d.py`)
- The 0D model gives the centre density n₀ and the sheath-edge density n_s = h_l n₀. The profile between them is the cosine solution of ambipolar diffusion with uniform ionization, n(x) = n₀ cos(kx), with k fixed so that n reaches n_s at the sheath edge.
- Tests: symmetric, peaks at n₀, equals n_s at both sheath edges. **Changed from the plan:** the plan said "its average equals the 0D n_e", but the 0D model's n_e is the centre density n₀, so the test checks the centre and edge values instead.

**3d — Sweeps** (`stage1/sweep.py`)
- Up to 200 points over power, pressure, Ar flow or admixture fraction. A point that fails is recorded with its reason and the sweep carries on.
- Tests: the requested number of points; a failed point is kept as a failure and the others are kept; 200 points in ≤ 120 s (PER-4).

**3e — N₂ and O₂ mixtures** (`stage1/mixtures.py`; rules fixed 3 November 2026, before any code)
- Four modes (Ar, Ar+N₂, Ar+O₂, Ar+N₂+O₂). Each admixture is a percentage of the Ar flow (1–10 %, default 5 %), so its mole fraction is f / (1 + f_N₂ + f_O₂). 0 % switches the admixture off, and then the pure-argon model runs unchanged.
  - ⚠ The supervisor has not confirmed whether N₂ and O₂ go in together (SUPERVISOR_QUESTIONS.md, Q5), so all four modes are built.
- Built in two steps, each tested and committed: **3e-1** argon + N₂ (several positive ions, no negative ions), then **3e-2** oxygen (O⁻, O atoms, O₂(a¹Δ), electronegative transport). **As built:** both live in one module (`mixtures.py`) and were committed together, after argon + N₂ had been run and checked on its own first.
- **Electron collisions with N₂ and O₂:** integrated from the Biagi cross-sections with the chosen EEDF, like argon. This covers ionization (N₂⁺, O₂⁺), all excitations as energy losses, dissociative attachment O₂ → O⁻ + O, dissociation of O₂ (the two "DISOC" states, 6.1 and 8.4 eV, each giving two O atoms), O₂(a¹Δ) excitation and N₂(C) excitation (needed for the 337 nm band in Phase 4). The O₂ three-body attachment is left out: it is normalized to gas density, and at an O₂ partial pressure of about 0.02 mbar it is negligible.
- **Argon with the molecules** (sources read directly):
  - **Charge transfer** (Anicich, *J. Phys. Chem. Ref. Data* 22, 1469, 1993, evaluated values at 300 K, ±20 %): Ar⁺ + N₂ → N₂⁺ + Ar, 1.10×10⁻¹⁷ m³/s; Ar⁺ + O₂ → O₂⁺ + Ar, 4.60×10⁻¹⁷ m³/s. (The 2026 CCP paper below uses 1.2×10⁻¹⁷ for O₂; the evaluated compilation is preferred.)
  - **Metastable quenching by N₂:** 3×10⁻¹⁷ m³/s in total (Le Calvé & Bourène 1973, as cited in arXiv:1104.5373). Of this, 2.8×10⁻¹⁷ m³/s goes to N₂(C) at 300 K (Pothiraja, Bibinov & Awakowicz 2010, as cited in arXiv:1109.5620).
  - **Metastable quenching by O₂:** Dong et al., arXiv:2601.08138 (2026), a CCP Ar/O₂ global model, Table A1, rows 31 and 33: 1.12×10⁻¹⁵ (to ground) and 5.8×10⁻¹⁷ m³/s (dissociating O₂). Row 31 is several times faster than two atoms colliding at their thermal speed would suggest. It is used as published and flagged here.
  - **Applied to metastables only:** both quenching sources concern metastables. 4p atoms radiate about a thousand times faster than they could be quenched.
- **Oxygen chemistry (3e-2):** from Dong et al. (2026) Table A1, with Kemaneci et al. (arXiv:1612.07268) Tables IV–VIII where Dong gives nothing.
  - **Electron reactions** with O, O⁻ and O₂(a), and O₂⁺ dissociative recombination: Dong rows 16, 21 and 23–26.
  - **Detachment:** O⁻ + O → O₂ + e (row 27); O⁻ + O₂(a) → O₃ + e (row 28; O₃ is not tracked, so it counts as a loss).
  - **Ion–ion recombination:** O⁻ with every positive ion at Dong's row 19 value, 1.5×10⁻¹³ (300/T_g)^0.5 m³/s. **Flagged:** Dong's row 36 gives O⁻ + Ar⁺ as 2.7×10⁻¹⁷, about 10⁴ times below every other ion–ion recombination in both tables. It looks like a misprint, but we will not "correct" a source from memory, so the row 19 value stands in for all positive ions. Ion–ion recombination depends only weakly on which positive ion takes part.
  - **Wall losses:** O atoms recombine at the walls with probability γ = 0.09 (Kemaneci Table VIII). O₂(a) is quenched at the walls with γ = 0.007 (Dong row 93). Both use Chantry's formula. Their diffusion coefficients are the argon-metastable value scaled by √(reduced mass of Ar–Ar / reduced mass of species–Ar), the Chapman–Enskog mass dependence with the same collision size; this approximation is stated in the code.
  - **Oxygen atoms are conserved:** O₂ + O₂(a) + O/2 equals the O₂ fed in.
- **Transport with several ions:** each positive ion has its own Bohm speed and edge factor, from its own mass.
  - **With O⁻ present** (degree of electronegativity α = n₋/n_e), each edge factor is divided by (1 + α), and the Bohm speed is multiplied by √((1+α)/(1+αγ)) with γ = T_e/T_g. When attachment is faster than ambipolar diffusion the factor becomes 1 (Kemaneci et al. 2016, Eqs. 6, 7 and 11–14). O⁻ ions are held inside the plasma and are not lost to the walls.
  - **Changed 3 November 2026, during development, before any comparison with data:** the Bohm factor now uses the electronegativity at the sheath edge, α_s = α₀ (n_e,edge/n_e,centre)^(γ−1), as Kemaneci's Eq. 11 defines it for Boltzmann negative ions. The rule above had used the centre value α₀. With γ ≈ 110 that cut the ion exit speed about threefold at only 1 % O₂ and made n_e rise with O₂, the opposite of the measured trend in Ar/O₂ CCPs. With α_s, n_e falls as O₂ is added (3.2 → 2.6 × 10¹⁶ m⁻³ at 5 % O₂).
  - **The collisional Child law** uses the flux-weighted ion mass.
- **Left out, stated:** N₂ dissociation and N atoms (Biagi has no explicit dissociation channel); N₂⁺ dissociative recombination (a source exists only for some channels; estimated at about 10 % of N₂⁺ loss); NO, O₃ and O₂(b) as tracked species; and gas heating by dissociation.
- **Rates at the Druyvesteyn EEDF:** rates taken from Maxwellian fits (the excited-state, O, O⁻ and O₂(a) electron reactions) are evaluated at the model's T_e. This approximation is stated, as for argon.
- **Solver:** the mixture unknowns are solved together, starting from the pure-argon solution and stepping the admixture up from 0 % to the requested value.
- **Tests:** a 0 % admixture reproduces the pure-argon result exactly; every balance closes below 10⁻⁸; charge and oxygen atoms are conserved; adding N₂ or O₂ lowers the metastable density; adding O₂ makes the plasma electronegative (α > 0); the four modes converge over the envelope.

**Exit gate**
- [x] Tests pass. (195 passed, plus the Phase 2 benchmark test still marked as an expected failure, 3 November 2026.)
- [x] The argon-only results from Phase 2 are unchanged with the new effects switched off (regression test). (Exact-value tests in `test_global_model.py`, `test_gas_flow.py`, `test_gas_temperature.py` and `test_mixtures.py`.)
- [x] `BUILDING_JOURNEY.md` has its Phase 3 section.

**Commit:** `Phase 3: Stage 1 gas flow, gas temperature, N2/O2 mixtures, 1D profile, sweeps`

---

## Phase 4 — Virtual OES

**Goal:** turn the plasma state into a spectrum and analyse it (Module 3; FR4.x and FR5.x).

Built in five steps, each tested and committed. The rules for 4a–4d were fixed on 3 November 2026, before any code. Those for 4e are written before 4e starts.

**Data added for this phase:** the LXCat **BSR** database (Zatsarinny & Bartschat, R-matrix), with electron collisions from the argon ground state and from each of the four 1s levels (177 processes). It is local only, like Biagi (`data/reference/README.md`). The file itself pairs each Racah level name with its Paschen name, so the mapping is not taken from memory.

**4a — Collisional-radiative model** (`oes/cr_model.py`)
- **Levels:** the four 1s levels (1s5, 1s4, 1s3, 1s2) and the ten 2p levels, each on its own. The ground-state density is the model's argon density.
- **Electron excitation:** from the ground state to every 1s and 2p level, and from every 1s level to every 2p level and to the other 1s levels, all integrated from the BSR cross-sections with the chosen EEDF.
  - The reverse (de-excitation) rates come from the same cross-sections by detailed balance on the cross-section (the Klein–Rosseland relation σ_ji(ε) = (g_i/g_j)·((ε+ΔE)/ε)·σ_ij(ε+ΔE)). This keeps them right for a non-Maxwellian EEDF.
- **Ionization from 1s and 2p:** the same published fits as Phase 2d (Kemaneci Table III, rows 8 and 15).
- **Radiation:** every 2p → 1s line in the NIST Ar I file, matched to its levels by energy (within 0.01 eV).
  - The two resonant 1s levels radiate to the ground state at the trapped rate already used in Phase 2d (1×10⁵ s⁻¹, Kemaneci row 23).
  - Every 2p → 1s line is reduced by Mewe's escape factor, γ = (2 − exp(−10⁻³κ₀R)) / (1 + κ₀R), with κ₀ = n_lower·A·(g_u/g_l)·(λ³/8π)·√(M/2πkT) (as written in arXiv:2402.08092, Eqs. 27–28, citing Mewe 1967). R is half the electrode gap, the shortest way out of the slab-shaped plasma; this choice is stated in the code.
- **Losses of 1s atoms:** diffusion to the walls (Chantry's formula, Phase 2d) and, in mixtures, quenching by N₂ and O₂ (Phase 3e rates).
- **Left out, stated in the code:** cascades from levels above 2p (3d, 2s and higher); 2p quenching by ground-state atoms (thousands of times slower than radiation at 0.1–0.5 mbar); and metastable pooling (a few per cent of 1s loss in Phase 2d). Without pooling, the balances are linear for given escape factors, which are found by repetition.
- **Inputs:** T_e, n_e, the EEDF, the gas density and temperature, and the geometry, all from the global model. The CR model reads the plasma state; it does not change it.
- **Tests:** populations are positive and rise with n_e; the populations satisfy every balance (residual < 10⁻⁹); with electron collisions off nothing is excited (changed from "leaves only the excitation sources": the sources are themselves electron collisions); the escape factor is 1 in a thin plasma and falls as the plasma gets thicker.
- **As built (3 November 2026):**
  - **Two additions:** a second NIST download, Ar I at 1000–1400 nm, because some 2p levels also decay by infrared lines beyond 1000 nm (2p10 → 1s3 near 1047 nm). 29 lines in all.
  - **A finding, recorded rather than hidden.** The BSR rates destroy the metastable 1s5 more slowly than the lumped published rates in the Phase 2d global model:
    - 1s5 → other 1s levels: 3.6×10⁻¹⁴ against 3.7×10⁻¹³ m³/s;
    - 1s5 → 2p: 5×10⁻¹³ against 9×10⁻¹³ m³/s, at T_e ≈ 3 eV.
    - So at the defaults the CR model's 1s5 density (6.5×10¹⁷ m⁻³) is about four times the global model's lumped metastable density. The CR model reads the plasma state and does not change it, so both are reported. Switching the global model to the BSR rates would change the Phase 2 and 3 results; it is an open decision, not done here.

**4b — Synthetic spectrum** (`oes/spectrum.py`)
- **Line power:** each line emits n_upper·A·γ·hc/λ (W/m³), at its NIST air wavelength.
- **Line shape:** a Gaussian combining the instrument function (FWHM from `envelope.toml`, default 0.005 nm) with Doppler broadening at the gas temperature, added in quadrature.
- **Grid and noise:** the wavelength grid runs between the envelope limits, five points per FWHM. Noise is Gaussian, as a percentage of the peak, from a seeded random generator (REL-4).
- **Tests:** the peaks sit at the NIST wavelengths; the area under each line equals its power; the same seed gives the same spectrum; recomputing takes ≤ 3 s (PER-2).

**4c — Boltzmann plot** (`oes/boltzmann.py`)
- Fit ln(Iλ/(gA)) against the upper-level energy; the slope is −1/T_exc. Report T_exc with its standard error and R².
- **E9 rule:** a fit with fewer than 4 lines, or an energy span under 1.0 eV, is flagged as unreliable (`envelope.toml`). The 2p levels span only about 0.6 eV, so a Boltzmann plot from 2p lines alone is always flagged; this is a true property of argon, not a fault.
- **Never mislabelled:** the result is called the excitation temperature everywhere, never T_e (exit-gate rule).
- **Tests:** a perfect Boltzmann population gives back its own temperature; the E9 rule triggers as stated.

**4d — Line-ratio T_e** (`oes/line_ratio.py`)
- Fit T_e and n_e together by matching the CR model's normalized 2p → 1s line intensities to the spectrum's, by least squares on log intensities. Gas density, gas temperature and geometry are taken as known.
- **Tests:** from a noise-free synthetic spectrum, the fitted T_e is within ±30 % of the model T_e (ACC-2). In fact it should come back almost exactly, and the test records how closely.
- **As built (3 November 2026):** noise-free, T_e and n_e come back within 10⁻³ (27 lines); with 1 % noise, T_e is within about 1 %. **Known limitation:** with 5 % noise the fit fails (T_e +216 %). Weak lines, whose A values are up to 1000 times smaller, are swamped by noise, and the unweighted log fit trusts them as much as the strong ones. Weighting each line by its uncertainty is the standard fix. It is a change of method, so it is recorded as future work and not slipped in.

**4e — Gas temperature and the N₂ band** (`oes/gas_temp.py`, `oes/n2_band.py`; rules fixed 3 November 2026, before any 4e code)
- **Doppler gas temperature:**
  - **E8:** enabled only when the instrument FWHM is no larger than the expected Doppler FWHM at the model's gas temperature. At 300 K the Doppler FWHM of the 750.4 nm line is about 0.0015 nm, so at the default 0.005 nm it is disabled.
  - **Method:** fit a Gaussian (centre, width, height, flat background) to the 750.387 nm line (2p1 → 1s2: the 2p1 level has essentially one decay route, and 1s2 is not metastable). Then FWHM_D = √(FWHM_fit² − FWHM_instrument²) and T = (FWHM_D/λ)² Mc²/(8k ln 2). In the synthetic spectrum, self-absorption lowers a line's power but not its shape; for measured spectra, an optically thick line would read too hot, and this is stated.
- **N₂ second positive bands (C³Π_u → B³Π_g) in the spectrum, when N₂ is present:**
  - **Band data from Gilmore, Laher & Espy, *J. Phys. Chem. Ref. Data* 21, 1005 (1992), Table 9** (NIST-hosted reprint): band wavenumbers, Franck–Condon factors and Einstein coefficients (integration method), for v' = 0 and 1, v'' = 0–10. Stored as `data/reference/constants/n2_second_positive.csv`, values read from the table.
  - **How much N₂(C) is made:** from the 3e mixture model (electrons and Ar*). It is split between C(v'=0) and C(v'=1) by X(v=0) → C(v') Franck–Condon factors. We compute those from Morse potentials built from the NIST constants of X, B and C (Huber & Herzberg). The method is accepted only if the same code reproduces Gilmore's C → B factors q₀₀, q₀₁ and q₁₀ within 5 %. Population of C(v') = production × FC / (sum of its A values). C(v' ≥ 2) is not drawn. N₂(C) quenching is neglected (about 10⁴ s⁻¹, against radiation at 2.7×10⁷ s⁻¹).
  - **Rotational structure, singlet approximation:** the triplet bands are treated as ¹Π–¹Π (P, Q and R branches) with the ΔΛ = 0, Λ = 1 Hönl–London factors (Herzberg), which a test checks against the sum rule. The triplet splitting is ignored: this is enough for the model to fit its own spectra, but a fit to a real high-resolution spectrum would need the full ³Π–³Π treatment. That limitation is stated in the code.
  - **Energy levels:** F(J) = B_v J(J+1) − D_v J²(J+1)², with B_v = B_e − α_e(v+½) and D_v = 4B_e³/ω_e² (the Kratzer relation; a test checks it against NIST's estimated D_e for B and X). The band origin is Gilmore's measured wavenumber.
  - **Intensities:** upper rotational levels in Boltzmann equilibrium at the gas temperature; each line's power ∝ ν⁴ × Hönl–London factor × population, scaled so the band adds up to its total power.
  - **Vacuum to air:** wavenumbers are converted to air wavelengths with the Peck & Reeder (1972) refractive index used by NIST ASD. A test checks it against the NIST argon lines (vacuum wavenumber from the level energies against NIST's air wavelength).
- **N₂ rotational temperature:** least-squares fit of the model (1,0) band, through the instrument, to the spectrum between 312.0 and 316.2 nm. The fit parameters are T_rot (bounds 200–2000 K), a scale and a flat background.
- **NH overlap check** (for measured spectra): the power in 335.8–336.2 nm (the NH A–X head) is compared with the N₂ (0,0) head window, 336.9–337.2 nm. More than 5 % is flagged. The model has no hydrogen, so its own spectra never trigger it.
- **Tests:** Doppler is disabled at 0.005 nm (E8), and at 0.001 nm it recovers the gas temperature within 10 % from a noise-free spectrum; the Hönl–London sum rule; Kratzer against NIST; Morse against Gilmore; air wavelengths against NIST; T_rot from a noise-free band within 1 % of the gas temperature, and within 10 % with 1 % noise; N₂ bands appear only when N₂ is present.
- **As built (3 November 2026):**
  - **Checks passed:** Morse against Gilmore (q₀₀ 0.469 against 0.454, q₀₁ 0.324 against 0.327, q₁₀ 0.398 against 0.392); Kratzer against NIST (B within 0.9 %, X within 0.4 %); air wavelengths within 1.5×10⁻⁴ nm of NIST.
  - **Gas temperatures recovered:** Doppler gives 301.999 K against the model's 302.00 K at 0.001 nm resolution. The noise-free N₂ rotational temperature is exact.
  - **Changed: the NH check.** The rule above compared the raw 336 nm power with the (0,0) head. The (0,0) band itself reaches past 336 nm, so that gave a false alarm (0.17) on a spectrum with no NH. It now subtracts what the (0,0) band at the fitted temperature puts there, and flags only the excess.
  - **Clarified: "within 10 % with 1 % noise".** Noise is a percentage of the spectrum's own peak. On a 300–900 nm acquisition that peak is the 811 nm argon line, so inside the much weaker N₂ band the noise is large, and T_rot misses by 16–29 % (three seeds). On a UV acquisition (305–340 nm), T_rot is within 0.7 %. Both results are recorded. The test uses the UV acquisition, which is how the band is measured in practice.
- **O I lines (777 and 844 nm): moved to Phase 7.** Excitation data for atomic oxygen are not in hand, and Phase 7 (underwater OES) needs them anyway. Phase 4 does not draw O I lines; changed from the original plan with this reason.

**Tests** (`tests/test_cr_model.py`, `test_spectrum.py`, `test_boltzmann.py`, `test_oes_gas_temp.py`, `test_line_ratio.py`)
- Populations are positive and increase with n_e.
- The spectrum peaks sit at the NIST wavelengths.
- A perfect Boltzmann population gives back its own temperature.
- The line-ratio T_e from a noise-free synthetic spectrum is within ±30 % of the model T_e (ACC-2).
- Doppler is disabled at 0.005 nm resolution.
- Recomputing the spectrum takes ≤ 3 s (PER-2).

**Exit gate**
- [x] Tests pass. (245 passed, plus the Phase 2 benchmark test still marked as an expected failure, 3 November 2026.)
- [x] T_exc is never labelled as T_e anywhere in the outputs. (`BoltzmannFit.excitation_temperature_ev`, checked by a test; T_e appears only where it truly is the electron temperature, as in the line-ratio fit.)
- [x] `BUILDING_JOURNEY.md` has its Phase 4 section.

**Commit:** `Phase 4: virtual OES - CR model, spectrum, Boltzmann plot, gas temperature`

---

## Phase 5 — Virtual Langmuir probe and comparison

**Goal:** the Stage 3 probe on the Stage 1 plasma, plus the three-way comparison (Module 4; FR6.x and FR7.x).

**Build**
- `probe/iv_model.py`:
  - The I-V curve of a cylindrical tungsten probe (default 0.195 mm × 5 mm, −20 to +50 V in 0.5 V steps), with OML ion current.
  - RF sheath-oscillation averaging at 13.56 MHz.
  - Seeded noise.
- `probe/analysis.py`:
  - V_f, V_p (from the zero crossing of d²I/dV²), T_e, n_e and λ_D.
  - The OML validity check r_p/λ_D ≤ 1 (E12).
  - A report of the step at which the analysis failed (E11).
- `probe/eepf.py`: the Druyvesteyn second-derivative EEPF with documented smoothing.
- `compare/diagnostics.py`:
  - Model vs OES vs probe values, with the deviation and a pass flag at ±30 %.
  - Dependent values marked: the OES n_e is taken from the probe and is not counted as an independent agreement.

**Rules** (fixed 3 November 2026, before any Phase 5 code)
- **Where the probe sits and what it sees:** the probe is at the discharge centre, so it sees n_e = n₀ and the model's EEDF (shape and T_e). In mixtures, the positive-ion density is n_e + n₋, by ion species.
- **Plasma potential against ground:** V_p = T_s/2 + V_f, the presheath plus the floating sheath at the large grounded chamber wall. It comes from the model's own wall constants: about 12 V at the defaults, inside the −20 to +50 V sweep. The symmetric-electrode RF sheath voltage of the global model (hundreds of volts) is not used: the probe is referenced to the grounded chamber, as in the laboratory.
- **Electron current below V_p (retarding):** I_e = (A e n/4) √(2e/m) ∫_V^∞ √ε F(ε)(1 − V/ε) dε, where V = V_p − V_probe. This is the same physics as `probe/retardation.py`, and it holds for any convex probe (Chen 2003, Lecture Notes on Langmuir Probe Diagnostics, Sec. V.A). Probe area A = 2π r L (the end face is ignored, about 1 % for the default probe).
- **Electron current above V_p:** the OML cylinder law for a Maxwellian at the screening temperature T_s, I_e(V_p)·[2√(η/π) + e^η erfc √η] with η = (V_probe − V_p)/T_s. It is continuous at V_p. This is an approximation for a non-Maxwellian EEDF; the analysis uses only the region below V_p.
- **Ion current:** the OML limit, I_i = A n_i e (√2/π) √(e(V_p − V_probe)/M) below V_p and zero above (Chen 2003, Eq. 22), summed over ion species. OML needs r_p/λ_D ≤ 1 (E12). At our densities λ_D ≈ 0.07 mm < r_p = 0.195 mm, so OML is formally outside its range. The validity check reports this, and the curve is still drawn with OML, as Chen notes OML "may give good results outside of its intended range".
- **RF distortion:** the plasma potential oscillates as V_p + Ṽ sin ωt, and the probe current is averaged over one period (64 phases). Ṽ is a probe setting, the RF amplitude left after compensation: 0–50 V, default 0 V (a fully compensated probe). The supervisor asked for distortion to be modelled (D5); its size depends on the laboratory probe's compensation (SUPERVISOR_QUESTIONS.md, Q8).
- **Noise:** Gaussian, as a percentage of the electron current at V_p, seeded.
- **Analysis**, step by step; a failure reports the step it failed at (E11):
  1. V_f: the zero crossing of the total current.
  2. Ion fit: OML says I_i² is linear in V. Fit I² against V on the points below V_f − 0.5 (V_p − V_f)-equivalent. In practice this is the lowest 40 % of the voltages below V_f, at least 5 points. Extrapolate and subtract it.
  3. V_p: the zero crossing of d²I_e/dV² (FR6.6), with derivatives from a Savitzky–Golay filter (window 5 points, cubic; documented smoothing). The crossing is linearly interpolated between points.
  4. EEPF and EEDF by Druyvesteyn's formula, n F(ε) = (4/(A e))·√(m/(2e))·√ε·d²I_e/dV². It follows from twice differentiating the retarding-current integral above; the code shows the derivation. In joules it is the textbook 2√(2mE)/(e²A)·d²I/dV². Then n_e = ∫ nF dε and T_eff = (2/3)⟨ε⟩.
  5. Slope T_e: the inverse slope of ln I_e between V_f and V_p (the same window as run 3).
  6. Debye length λ_D = √(ε₀ T_eff/(e n_e)) and the OML check.
- **Comparison (`compare/diagnostics.py`):** T_e, n_e and T_gas from the model, OES and probe.
  - **Deviation:** each diagnostic's deviation from the model; pass if |deviation| ≤ 30 % (`envelope.toml`). A quantity passes when every independent diagnostic passes. The verdict counts the passing quantities.
  - **T_e:** the probe's EEPF T_eff (same definition as the model) is compared. The slope T_e is shown but not counted.
  - **T_gas:** OES gives it from N₂ T_rot (when N₂ is present) or Doppler (when E8 allows).
  - **Dependent values:** following the supervisor (Q2), by default OES takes n_e from the probe and fits only T_e, so its n_e is marked dependent and excluded (FR7.2). The option to fit both is kept.
  - **Excitation temperature:** T_exc is shown and excluded, with the reason (FR7.5).
  - **With O₂:** probe and OES results are flagged approximate (LI-4). Negative ions change the probe's ion current, and the argon CR model ignores O₂ chemistry beyond metastable quenching.
  - Each method's assumptions are listed from the settings used (FR7.6).

**As built (3 November 2026): changes to the rules above and findings, each made before any comparison with data**
- **Ion fit, as implemented:** the I² fit uses the lowest 40 % of the points below V_f, at least 5 (the rule's wording above was garbled). Then a **second pass** refits I² = a·(V_p − V) with its zero fixed at the first-pass V_p, because OML puts the ion current's zero exactly at V_p (Chen Eq. 22). A free fit reached zero at 8.5 V instead of 12 V, and that kink made a false spike in the Maxwellian EEPF at 3–4 eV.
- **Noise robustness, three changes:**
  - **V_f:** the last negative-to-positive crossing, because noise made false crossings deep in the ion region.
  - **V_p:** the d²I/dV² zero crossing nearest the peak of dI/dV, because noise made many crossings. Still a zero crossing, as FR6.6 asks.
  - **Ion-fit fallback:** a straight line, or else a constant, each with a warning, when noise spoils the I² fit.
- **EEPF reliability flag (new):** a single sweep with 1 % noise cannot give an EEPF; the second derivative turns noise into a false tail, inflating T_eff by about 200 %.
  - **The rule:** the point-to-point noise is measured from second differences of the ion-fit residual (blind to smooth misfit). From it, the expected false density and false mean energy that clipped noise adds are computed. The EEPF is trusted only if both are ≤ 5 %.
  - **In practice:** at the 0.5 V step this allows about 0.001 % noise; at the default 1 %, the EEPF is flagged and the probe's T_e and n_e are not counted in the comparison.
  - **What was tried and dropped:** cutting the EEDF at its first zero past the peak did not work, because the peak itself became a noise spike. It was removed, not kept.
- **Added: the saturation density,** n = I_e(V_p)/(A e √(eT_slope/2πm)). It is the textbook random-flux formula and stands up to noise: within 6 % at 1 % noise. It is shown alongside n_e(EEPF), and OES uses it for n_e when the EEPF is flagged.
- **Finding: the V_p bias.** Just above V_p the cylindrical OML electron current has a second derivative that plunges towards −∞, so the zero crossing sits low: by 0.16 V at a 0.1 V step and 0.58 V at the default 0.5 V step. At 0.5 V this makes n_e(EEPF) 14 % low (T_eff within 4–8 %).
  - **The ACC-2 test (±10 %)** uses a 0.1 V step, where n_e is within 4–6 % and T_eff within 1.3 %. The 0.5 V bias is pinned by its own test.
  - **An exact test** shows the V_p offset is the only error: recovered(ε) = √(ε/(ε+δ))·true(ε+δ), within 3 %.
- **Finding: borrowing n_e makes OES T_e sensitive.** With n_e taken from the probe (the supervisor's Q2 route), a 10–14 % low n_e makes the line-ratio T_e 29–35 % high, because two-step excitation ties the line pattern to n_e. So at the defaults (probe noise 1 %), only OES T_e counts, and it misses (+34 %). With a noise-free probe in argon, 1 of 2 quantities agree. With 5 % N₂, all 3 agree (T_e: OES +29 %, probe −3 %; n_e: probe −14 %; T_gas: +1 %).

**Tests** (`tests/test_probe_iv.py`, `test_probe_analysis.py`, `test_eepf.py`, `test_compare.py`)
- A noise-free curve recovers the model T_e (as T_eff, the EEPF mean-energy definition) and n_e within ±10 % (ACC-2); the slope T_e matches `probe_style_te` of the same EEDF.
- The EEPF recovered from a Druyvesteyn plasma is Druyvesteyn-shaped.
- The comparison flags 31 % as a fail and 29 % as a pass.
- Generation plus analysis takes ≤ 2 s (PER-3).

**Exit gate**
- [x] Tests pass. (280 passed, plus the Phase 2 benchmark test still marked as an expected failure, 3 November 2026.)
- [x] Results with O₂ present are flagged as approximate (LI-4). (`test_oxygen_results_are_flagged_approximate`: flagged, and nothing counts as agreement.)
- [x] `BUILDING_JOURNEY.md` has its Phase 5 section.

**Commit:** `Phase 5: virtual Langmuir probe, OML analysis, EEPF, diagnostics comparison`

---

## Phase 6 — Stage 1 dashboard and sessions

**Goal:** a usable Stage 1 application that matches mockups M1–M7 (Modules 1 and 7).

**Build**
- `storage/sessions.py`: save, list, search, open, compare (2–5) and delete sessions, using parameterised queries only (SEC-4). Session IDs run S-0001, S-0002, …
- Streamlit pages for each screen:
  - M1 Home: quick start, recent sessions, role switch, reference-data status.
  - M2 Chamber configuration: live validation messages from `envelope.toml`.
  - M3 Results.
  - M4 Virtual OES.
  - M5 OES analysis.
  - M6 Langmuir probe.
  - M7 Comparison.
  - A basic M11 session list.
- Caching keyed on the configuration hash (PER-1). The server is bound to 127.0.0.1 only (SEC-1).
- Every chart has a symbol and an SI unit on each axis (USE-4). Every status message has text as well as colour (USE-5).

**Rules** (fixed 3 November 2026, before any Phase 6 code)
- **Layers:**
  - Screens live in `app/` and contain no physics.
  - An application-service layer, `plasma_twin/services/stage1.py`, turns screen values into model inputs. It runs the model, the OES and the probe, turns results into plain JSON for storage, and writes CSV exports.
  - `plasma_twin/` still never imports Streamlit.
- **Sessions (`storage/sessions.py`):** every SQL statement uses `?` placeholders (SEC-4). **Changed while building:** text search now runs in Python on the note and the configuration *values*, so typed text never reaches SQL and searching "power" does not match every session's field names. The first version, a SQL LIKE with `%`/`_` escaped, matched the JSON field names. IDs are shown as S-0001 from the AUTOINCREMENT key, so a deleted ID is never reused (FR3.9). `delete_sessions` refuses to act unless it is called with `confirmed=True`, and the screen only passes that after a second click. Comparison takes 2–5 sessions of the same stage (FR11.2). Each session stores the model version (`plasma_twin.__version__`); reopening a session from another version says so and offers a re-run (FR11.3).
- **Example experiments (FR1.2, FR2.9):** named presets in `plasma_twin/config/presets.toml`, each checked against the envelope by a test. The Home screen has one button, "Run the default experiment", which runs the model and opens the Results screen: one click (USE-1, ≤ 2).
- **Caching (PER-1):** every model, OES and probe run is cached by the SHA-256 of its inputs written as sorted JSON, the same hash stored as `config_hash`.
- **Charts:** Plotly, with a symbol and an SI unit on every axis (USE-4). The 300–900 nm spectrum has about 600,000 points at 0.005 nm, too many to draw. It is drawn reduced to about 4,000 bins, keeping each bin's highest value so no line peak is lost; the export keeps every point.
- **Status messages:** every one has words as well as colour (USE-5).
- **Roles:** Student and Researcher are switched in the sidebar without logging in (FR1.4). The Researcher-only parts that need imported data (FR4.6, FR5.1) say they come in Phase 8.
- **M11 here is basic:** list, filter, search, open, compare and delete, with CSV export. The PDF report and the non-citable-data rule (FR11.5, E19) come with imports in Phase 8.
- **Checks:** unit tests for sessions and the service layer. Every screen is smoke-run headless with Streamlit's own `AppTest` (no exceptions, key elements present). The full M1 → M7 workflow is then clicked through in the browser.

**As built (3 November 2026)**
- **Screens:** `app/Home.py` (M1) and `app/pages/1_…` to `7_…` (M2–M7, M11 basic), with shared glue in `app/common.py`. Services are in `plasma_twin/services/stage1.py`, sessions in `plasma_twin/storage/sessions.py`, and presets in `plasma_twin/config/presets.toml`.
- **Browser check of the full workflow, by clicking:** Home → one-click default experiment → Results → Virtual OES → OES analysis → Comparison → Langmuir probe → save a session → Sessions. A session saved there survived a full page reload. The test session was then removed.
- **Fixed during the check:**
  - Four metrics per row cut long values off in a narrow window, so metrics are now two per row.
  - On the probe screen, an unreliable EEPF's T_eff and n_e are labelled "UNRELIABLE (noise)".
  - "excitation temperature:" was repeated on the comparison screen.
  - Some envelope limits are whole numbers, and Streamlit refuses mixed number types, so they are now cast to float.
- **A development note:** the running server keeps imported modules, so after editing `app/common.py` it must be restarted. Page scripts reload by themselves.
- **Speed-up, no change to results:** each gas-temperature repetition now starts from the previous repetition's solution, with the cold start as a fallback. The answer must still close every balance to 10⁻¹¹. Pure argon with gas heating dropped from about 0.8 s to 0.09 s per run.
- **Timing tests and power:** run them with the laptop plugged in. On battery, Windows throttled the processor and the same unchanged code ran up to 5 times slower within seconds (four Phase 2 runs: 0.31 s, then 1.6 s). That made the 200-point sweep test fail once at 191 s (limit 120 s) before the warm start. With the warm start it passes even throttled (96 s).

**Requirement check, FR1.1–FR7.6 (3 November 2026, before the push)**
- **What was checked:** every requirement was compared with its SRS text and acceptance criterion. 16 gaps were found and fixed:
  - **Home:** FR1.1 (Diagnostics & data and AI entry points), FR1.3 (three recent sessions, "View all"), FR1.5 (AI model status).
  - **Chamber screen:** FR2.5 (disabled zero fields, flows in sccm), FR2.10 (model-regime note, plus a λ_i < s_m check on Results), FR2.12 (admixture sweep).
  - **Results:** FR3.10 (CSV header with session ID and version).
  - **OES screen:**
    - FR4.2: the toggles subtract the species' noise-free part, from `oes.spectrum.species_contributions`.
    - FR4.3: integration time.
    - FR4.5: E_k, g_k A_ki, relative intensity, and "in Boltzmann plot".
    - FR4.7: export header.
  - **OES analysis:**
    - FR5.4: populations against Boltzmann at T_e, from `oes.boltzmann.populations_vs_boltzmann`. A level counts as in equilibrium within a factor 2.
    - FR5.6: T_gas method choice.
  - **Probe:** FR6.1 (probe type and tip material), FR6.6 (OML n_e), FR6.8 (smoothing window shown).
- **The OML n_e (FR6.6):**
  - **Method:** n_i = (π b / (A e)) √(M / 2e). b is fitted linearly to the ion current, I_i = −b √(V_p − V), on the same fit points as the ion fit, with the final V_p. M is the OML-equivalent mass of the ion mixture, (Σn / Σ n M^−½)².
  - **Changed while building:** the first version took the slope of the I² fit. At the default 1 % noise that fit falls back (noise is as large as the ion current), so the value was not available on the default screen. The linear fit does not square the noise.
  - **Result:** within 1 % of the model with no noise. At 1 % noise it is 15–22 % off: the scatter of about 16 noisy points, inside ±30 %.
  - **The M7 comparison is unchanged:** the OML n_e is shown, not counted, because the Phase 5 rules are fixed.
- **Kept, with a note:**
  - **FR5.6:** Doppler uses 750.4 nm, not the SRS's 811.5 nm (self-absorption on 1s5, Phase 4e). The SRS text should follow.
  - **FR3.2:** the metastables are lumped in the global model.
- **Phase 8:** FR4.6, FR5.1 (imported), FR6.9.

**Tests** (`tests/test_sessions.py` plus manual checks in the app)
- Sessions survive a restart.
- Deleting a session asks for confirmation.
- Injection strings typed into notes and search do nothing.
- Each FR1.x–FR7.x requirement is checked by hand against its mockup. (Done 3 November 2026: `docs/validation/phase6_fr_checklist.md`.)

**Exit gate**
- [x] A new user runs the default experiment in ≤ 2 clicks (USE-1). (One click: the Home quick-start button opens Results; `test_quick_start_is_one_click_to_results`, and checked in the browser.)
- [x] The full M1→M7 workflow works in the browser. (Clicked through on 3 November 2026; see "As built".)
- [x] All tests pass. (315 passed, plus the Phase 2 benchmark test still marked as an expected failure. After the requirement check: 329 passed plus the same expected failure; one old CSV test was updated for the new export header and re-run.)
- [x] `BUILDING_JOURNEY.md` has its Phase 6 section.

**Commit:** `Phase 6: Stage 1 dashboard (M1-M7) and session management`

---

## Phase 7 — Stage 2 underwater plasma disinfection

**Goal:** the underwater pulsed-DC O₂ bubble discharge, through to *E. coli* survival (Module 5; FR8.x and FR9.x).

**Build**
- `stage2/pulse.py`:
  - Duty cycle = width × frequency, which must be < 1 (E5); a warning above 0.5.
  - Energy per pulse = P/f.
- `stage2/bubble_model.py`: a gas-phase global model of O₂ + water vapour with a Maxwellian EEDF, at 1 atm and a gap of 1, 2 or 3 mm.
- `stage2/liquid.py`:
  - Empirical transfer of O₃, H₂O₂ and OH into the water.
  - Changes in pH, ORP, conductivity and temperature.
- `stage2/hom.py`:
  - The Hom model log₁₀(N/N₀) = −k·Cⁿ·tᵐ, with k, n and m fitted to published time-resolved data.
  - The log reduction, the D-value and the energy yield.
  - ⚠ Find the published survival data before starting (UNDERSTANDING.md §8, item 4).
- `stage2/uw_oes.py`: OH at 309 nm, H-alpha at 656.3 nm and O I at 777/844 nm, with n_e from the H-alpha Stark width (Gigosos relation).
- Streamlit pages M8 and M9.

**Rules** (fixed 4 November 2026, before any Phase 7 code)

*Decisions taken with the student on 4 November 2026:*
- **Disinfection kinetics:** dissolved ozone, from Hunt & Mariñas (1997, *Water Research* 31, 1355). E. coli inactivation is first-order in both dissolved O₃ and live cells. The rate constant is 130 L mg⁻¹ s⁻¹ at 20 °C, with activation energy 37,100 J mol⁻¹. In Hom form log₁₀(N/N₀) = −k Cⁿ tᵐ, this is n = 1 and m = 1. Because C changes with time, the model uses the integral: log₁₀(N/N₀) = −(k_T / ln 10) ∫C dt.
  - k_T is k at the water temperature, from the Arrhenius law.
  - Their data covered O₃ = 6–41 µg/L and t = 1.8–33 s. Outside that range the result is flagged as extrapolated.
  - S. aureus and spores stay unavailable (LI-6).
- **Validation:** no open-access experiment matches our device (pin-to-pin, 1–10 kV, 5–10 kHz, O₂ bubbles). The papers searched, and why each was rejected, are recorded in BUILDING_JOURNEY.md. So:
  - **Part checks:** each part is checked against its own published data (below).
  - **End-to-end gate (ACC-1/BO-4):** stays **open**, waiting for the supervisor's time-resolved survival data (SUPERVISOR_QUESTIONS.md, Q13). This is the same treatment as Phase 2's open benchmark item.
  - **Li et al. 2020 (AIP Advances 10, 025207):** 35 kV sparks at 1 Hz, killing mainly by UV. It is outside our envelope and our mechanism, so it is shown as context only. Its H₂O₂ value is a sanity check: 0.19 mmol/L after 60 min with O₂ bubbling.
- **Electron–water data:** LXCat Itikawa H₂O set (Itikawa & Mason 2005), downloaded 3 November 2026. It is private, like the other LXCat files.

*Every number used in Stage 2 is read from a named source into `data/reference/constants/stage2_constants.csv` (value, unit, source, page or table) before it is used. No value is typed into the code from memory.*

- **Pulse (`stage2/pulse.py`):**
  - duty = width × frequency. The run is blocked at duty ≥ 1 (E5), with a warning above 0.5.
  - Energy per pulse = P/f.
  - Power during the pulse = P/duty.
- **Bubble gas:**
  - O₂ saturated with water vapour at the water temperature. The vapour pressure comes from the NIST WebBook Antoine coefficients for water.
  - "O₂ only" mode has no water. It disables OH, H₂O₂, H-alpha and the Stark n_e (FR8.9).
- **Bubble plasma (`stage2/bubble_model.py`), 0D, Maxwellian, 1 atm:**
  - **T_e:** during the pulse, T_e is where electron production equals electron loss by attachment. Production is ionization of O₂ (Biagi) and H₂O (Itikawa). Loss is dissociative attachment of O₂ (Biagi) and H₂O (Itikawa). At 1 atm the pulse sits at this balance (the attachment–ionization limit). Recombination and three-body attachment are not in the balance, and this is stated.
  - **Energy branching (G-values):** each electron process takes a share n_g k_j ε_j / Σ of the pulse energy. That gives the radicals made per joule: O(³P), O(¹D), OH, H, and ions. This needs no discharge volume.
    - O₂ dissociation channels follow the Biagi/Phelps convention: the 6.0 eV and 8.4 eV excitations dissociate to O+O and O+O(¹D).
    - OH comes from Itikawa's "OH(X)" neutral-dissociation cross-section.
  - **n_e (for Stark broadening only):** P_pulse = n_e V Σ n_g k_j ε_j e. V is a channel of length = gap and diameter from the measured minimal streamer diameter at 1 bar (Briels et al. 2008). The diameter is an assumption, stated with its source; n_e depends on it and a sensitivity is shown.
- **Afterglow gas chemistry:**
  - The radicals from one pulse react for one period (1/f), at the gas temperature.
  - The set is O, O(¹D), O₃, OH, H, HO₂, H₂O₂, O₂ and H₂O. Each rate comes from NASA JPL Publication 19-5 (open). O(¹D) + H₂O → 2 OH is included.
  - Output: O₃ and H₂O₂ molecules per pulse, hence per second (× f).
- **Liquid (`stage2/liquid.py`):**
  - **H₂O₂:** it is very soluble (Sander 2023 Henry constant), so all gas-phase H₂O₂ dissolves.
  - **O₃:** it dissolves through a two-film transfer, dC/dt = k_La (H p_O₃ − C) − k_d C.
    - H is the Sander 2023 Henry constant for O₃.
    - p_O₃ is the outlet-gas partial pressure: production ÷ O₂ flow.
    - k_d is ozone decay in water, from Staehelin & Hoigné, depending on pH.
    - k_La is the empirical part. It is read from a published bubble-column ozonation measurement before coding, and its source is shown in the app. If no source can be read, the rule is reported and the student decides.
  - **OH in the liquid:** steady state between the OH flux into the water and its reactions (OH + OH, OH + H₂O₂; Buxton et al. 1988 rate constants).
  - **COD:** COD is recorded. Its ozone demand is used only if a published first-order ozone-demand constant for municipal waste water can be read. Otherwise the model is stated as valid for low-organic water.
  - **Temperature rise** = deposited energy ÷ (water mass × specific heat), as the test says (FR9.5).
  - **pH and conductivity:** from the ions formed (H⁺, HO₂⁻). With O₂ only and no N₂, little acid forms. That is physics, and the screen says so.
  - **ORP:** shown as the Nernst potential of the O₃/O₂ couple. It is labelled a thermodynamic estimate: real ORP electrodes read lower.
- **Underwater OES (`stage2/uw_oes.py`):**
  - **Emission rates** use the Itikawa *emission* cross-sections: OH(A) 309 nm, H Balmer alpha, and O 777/844 nm from H₂O.
  - **O I from O₂ dissociative excitation** needs e–O₂ emission data we do not have. It is left out and stated.
  - **OH band shape:** the (0,0) band uses the OH constants already in `diatomic_constants.csv`, at the gas temperature. It is marked approximate (no spin splitting).
  - **H-alpha:** a Stark Lorentzian (Gigosos et al. 2003 FWHM–n_e relation), Doppler and the instrument.
  - **Stark n_e:** found by fitting the width, removing Doppler and the instrument, and inverting the relation. Only when the instrument FWHM < Stark FWHM (FR9.4).
- **Stage 1 O I lines (777/844 nm):** these need e–O excitation cross-sections, which are not downloaded. They stay disabled, and this is recorded as pending data.
- **Speed:** one 1 min run takes ≤ 10 s (PER-5).

**As built (4 November 2026)**
- **Code:**
  - `plasma_twin/stage2/`: `pulse.py`, `bubble_model.py`, `liquid.py`, `hom.py` and `uw_oes.py`.
  - `plasma_twin/services/stage2.py`.
  - Screens `app/pages/8_Underwater_configuration.py` (M8) and `9_Underwater_results.py` (M9).
  - Sessions and Home now handle Stage 2.
- **Data:** every number is read from `data/reference/constants/stage2_constants.csv`: 75 rows, each with its source and page, checksummed in the manifest. The LXCat Itikawa H₂O file is registered (private).
- **CHANGED WHILE BUILDING: the share of power that reaches the bubble gas.**
  - **What went wrong:** the first run put all 100 W into 100 sccm of O₂, about 14 eV per molecule. Every pulse split all the O₂, and no ozone came out. So the rule "all power into the gas, as an upper limit" does not give an upper limit: it breaks the model.
  - **Why:** real underwater discharges put most of their energy into the water. No published value for our device was found.
  - **What changed:** the share is now a visible input (envelope 0.01–1). Its default, 0.076, is the largest share that splits at most 10 % of the O₂ per pulse at the default operating point. That is the validity limit of the reaction set, which has no O + O + M. It is computed by `default_power_share()`, and a test keeps the envelope value equal to it.
  - **How it is shown:** M9 plots the log reduction and ozone against the share. Supervisor question Q19 asks for a measured value.
  - **Decision:** taken by Claude after the student said "complete it", following the recommendation offered.
- **Other choices made while building, each stated in its module:**
  - **Itikawa rows:** the "Total Ionization" row is used for ionization and the momentum-transfer row for elastic losses. The emission rows go only into the spectrum, not the energy balance. OH(X) dissociation has no threshold in the file, so its first tabulated energy (10 eV) is used.
  - **Hydrogen balance:** H₂ was added as a species, because H + HO₂ → H₂ + O₂ made the hydrogen balance leak 0.2 %.
  - **H-alpha acquisition:** H-alpha gets its own 650–663 nm acquisition, like the N₂ band in Stage 1. On the full range the OH peak sets the noise, and H-alpha (about 1,600 times weaker) is lost.
  - **Stark tolerance:** the noisy-Stark test tolerance (5 % at 1 % noise) was set after one look at three seeds (−2.2 to +0.9 %). Recorded here.
  - **O I:** Stage 1 O I lines stay disabled. They need e–O excitation data, which is not downloaded.
- **Results at the defaults:**
  - **Plasma:** T_e = 2.20 eV; n_e = 6.6×10¹⁹ m⁻³ in the channel, and 6.7×10¹⁹ m⁻³ back from the Stark fit.
  - **Chemistry:** ozone yield about 1 g/kWh; water vapour's HOₓ cycles destroy most O atoms (in dry O₂, 99 % become ozone). Dissolved O₃ is 0.6 mg/L after 1 min.
  - **Disinfection:** the log reduction hits the one-cell cap (7.9) and is flagged as extrapolated, because Hunt & Mariñas measured 6–41 µg/L and up to 33 s.
  - **Water:** temperature rises 2.9 °C.
  - **Speed:** one run takes 0.25 s (PER-5 allows 10 s).
- **Browser check:** M8 → run → M9, all sections present and the Stark n_e shown.

**Tests** (`tests/test_pulse.py`, `test_bubble_model.py`, `test_liquid.py`, `test_hom.py`, `test_uw_oes.py`)
- 100 µs at 10 kHz is blocked.
- 10 µs at 5 kHz gives a duty cycle of 5 % and 20 mJ per pulse.
- The Hom model reproduces its own fitted points.
- The temperature rise equals energy ÷ (mass × specific heat).
- The Stark width inverts back to the n_e that produced it.
- One run takes ≤ 10 s (PER-5).

**Exit gate**
- [x] Tests pass. (Phase 7: 24 unit tests and 2 screen tests; full-suite count in BUILDING_JOURNEY.md.)
- [ ] The log reduction is within ±30 % of the published reference at 1 or more points (ACC-1, BO-4). **Left open by team decision (4 November 2026):** no published experiment matches the device; waits for Q13.
- [x] Each part matches its own published data: Hunt & Mariñas first-order kinetics and Arrhenius reproduced exactly; Stark relation inverts exactly, and the fitted spectrum gives n_e within 0.1 % (no noise) and 5 % (1 % noise); temperature rise equals energy ÷ (m c); O and H atoms conserved in the afterglow; ionization balances attachment; energy shares sum to 1. (Li et al. 2020's H₂O₂ is context only: their sparks at 1 Hz are outside our envelope.)

**Commit:** `Phase 7: Stage 2 underwater bubble plasma, liquid chemistry, Hom model, underwater OES`

---

## Phase 8 — Measured data, validation and export

**Goal:** the Researcher features (Module 6) and export (Module 7) (FR10.x, FR11.5).

**Build**
- `data_io/importers.py`:
  - OES text files and probe `.csv` files, up to 50 MB.
  - Column mapping and unit conversion.
  - Mandatory metadata.
  - Rejection of bad files with the exact reason (E13/E14).
- `data_io/validation.py`:
  - Benchmarks and measured-data checks at ±30 %, with the tolerance read from the versioned config (CON-7).
  - Results recorded with date and software version.
  - Measured data never change model parameters (CON-6).
- `data_io/export.py`:
  - PDF, CSV and PNG exports.
  - The citation filter: non-citable data never appear in an export (SEC-3, E19).
- Streamlit page M10 (Researcher only), the M11 export panel, and the overlays in M4 and M6.

**Rules** (fixed 4 November 2026, before any Phase 8 code)
- **Files are data, never code (SEC-2):**
  - **Types:** an OES spectrum must be `.txt` and a probe I–V curve `.csv` (the supervisor's formats, Round 3 Q8).
  - **Rejected with the exact reason (E14), and nothing stored:**
    - a file over 50 MB (envelope `data.import_max_file_mb`);
    - a file containing a NUL byte (binary);
    - a file that is not UTF-8 or Latin-1 text;
    - fewer than two numeric columns;
    - fewer than 10 data rows;
    - a non-numeric or empty cell after the header (the row number is given);
    - an OES wavelength column that is not increasing.
  - **Header and delimiter:** leading lines that are not numbers are kept as the file's header, not data. The delimiter (tab, comma, semicolon or spaces) is detected from the first data lines, then the whole file is read with pandas' C parser (PER-7: 50 MB in ≤ 15 s).
- **Column mapping and units (FR10.3):**
  - **OES:** wavelength in nm and intensity in arbitrary units.
  - **Probe:** voltage in V and current in A, mA or µA, converted to A (× 1, × 10⁻³, × 10⁻⁶).
  - **Preview:** downsampled to at most 4,000 points, keeping peaks (as in Phase 6).
- **Mandatory metadata (FR10.2):**
  - **Every file:** diagnostic, plasma stage, gas mixture, measurement date (not in the future), instrument (not empty), and operating conditions inside that stage's envelope:
    - Stage 1: power, pressure, Ar flow, mixture and admixtures;
    - Stage 2: average power, frequency, pulse width, gap, O₂ flow, bubble gas.
  - **Probe files** also need the tip radius and exposed length, inside the probe envelope, because the analysis needs the probe area.
  - **OES files** also need the instrument FWHM, inside the OES resolution envelope. **Changed while building, before any result:** line integration and the H-alpha Stark width both need it.
  - **Probe files are Stage 1 only:** a Langmuir probe is not used in the underwater discharge (D1).
- **Storage and privacy (FR10.4, FR10.5, CON-6):**
  - **Where:** a saved file is copied byte for byte to `data/measured/<sha256>.<ext>`, made read-only, and recorded in `imported_files` with its metadata, mapping and units. `data/measured/` is gitignored, like the database, so measured data never leave the computer.
  - **Citation permission:** "Not citable" unless the Researcher ticks permission. Permission is fixed at save time; changing it means deleting and importing again.
  - **Cancel:** stores nothing.
- **Validation (FR10.6, FR10.7, CON-6, CON-7, ACC-4):**
  - **The tolerance** is read from `envelope.toml` (`validation.agreement_tolerance_fraction`, ±30 %), fixed before any comparison.
  - **Literature benchmarks:** the Saikia et al. (2018) points (Phase 2, unchanged rules). The Phase 2 gap stays visible as failures.
  - **Measured probe file (Stage 1):** analysed with exactly the M6 method (`probe.analysis.analyse`). It is compared with the model run at the file's conditions (default geometry, Druyvesteyn):
    - T_e: the EEPF effective temperature if the EEPF is reliable, otherwise the slope temperature (flagged);
    - n_e: the EEPF density if reliable, otherwise the OML ion density.
  - **Measured OES file, Stage 1:** line intensities are integrated at the CR-model lines, then a line-ratio fit gives T_e. Its n_e comes from a saved probe file at the same operating conditions if one exists; otherwise both T_e and n_e are fitted.
  - **Measured OES file, Stage 2:** n_e from the H-alpha Stark width (Phase 7 method), compared with the model's channel n_e. The power-share assumption applies.
  - **Recording:** every check is written to `validation_results` with date and software version. A check that cannot run (for example no lines in range) is reported as "not run" with the reason, never as a pass.
  - **Measured data never change model parameters (CON-6):** validation only reads data. A test checks that the model gives identical results before and after a validation run.
- **Export and the citation filter (FR10.8, FR11.5, E19, SEC-3):**
  - **Formats:** PDF (multi-page report with tables and figures), CSV and PNG, all made with matplotlib.
  - **Non-citable files appear only as anonymised entries:** "Measured file M-0003 (not citable): pass" or "fail". No file name, no metadata, no values, no curve.
  - **E19:** the number of non-citable files excluded is shown before every export.
  - **SEC-3:** a test exports with a non-citable file present and checks that none of its numbers, name or metadata appear in the PDF, CSV or PNG data.
- **Overlays and imported analysis (Researcher only, LI-9):**
  - **M4 (FR4.6):** overlays a saved Stage 1 OES file. Both spectra are normalised to the same reference line: the strongest model Ar I line inside both wavelength ranges, using each spectrum's peak within ±3 FWHM of it.
  - **M5 (FR5.1):** can analyse a saved Stage 1 OES file instead of the synthetic spectrum.
  - **M6 (FR6.9):** can analyse a saved probe file with the same method.
- **Sample files:** none have arrived from the supervisor yet, so that gate item waits. Small synthetic test files are made by the tests themselves, never committed as "measured data".

**As built (4 November 2026)**
- **Code:**
  - `plasma_twin/data_io/`: `importers.py`, `validation.py`, `export.py` and `overlay.py`.
  - `plasma_twin/storage/measured.py`, which uses the `imported_files` and `validation_results` tables from Phase 0.
  - Screen `app/pages/10_Measured_data.py` (M10).
  - Researcher overlays on M4 (FR4.6), M5 (FR5.1) and M6 (FR6.9); the export panel on Sessions (FR11.5); a Home entry for Researchers.
- **matplotlib 3.11.2** draws every PDF and PNG; kaleido would have needed a browser engine. It is pinned in `requirements.txt` with its dependencies.
- **Changed while building, before any result:** OES files must also give the instrument FWHM. Line integration and the H-alpha Stark width both need it (recorded under the metadata rule).
- **Fixed while building:**
  - **Error messages:** the first importer sniffed the delimiter from 20 lines, so one bad cell early on gave a vague "could not separate columns". It now takes the delimiter from the first data line, and every bad cell is reported by line and column.
  - **Speed:** reading every cell as text took 2.4 s for 11 MB, near the PER-7 limit at 50 MB. It now reads numbers directly and only falls back to text to locate a bad cell: 49 MB in 1.2 s.
  - **"Not run" is never a fail:** a NaN value (an OML density spoiled by noise) now counts as "not run".
  - **Upload limit:** Streamlit's uploader advertised 200 MB. `.streamlit/config.toml` now sets `maxUploadSize = 50`, and a test keeps it equal to the envelope.
  - **Screen tests:** they kept the cached stores of earlier tests. The test fixture now clears them, so each test has its own database.
- **How SEC-3 is tested:** the PDF is rendered uncompressed with Type 3 fonts, so the test can read back the text matplotlib drew. It checks that a non-citable file's name, instrument and values appear in neither the PDF nor the CSV, and that its anonymised entry does.
- **End-to-end check with files made by the model itself** (a self-consistency test of the import → analysis chain, not physics validation):
  - probe file, imported in mA: within 4 % (T_e) and 16 % (n_e);
  - Stage 1 spectrum, with n_e from that probe file: T_e within 1.4 %;
  - Stage 2 H-alpha: Stark n_e within 0.1 %.
  - The literature benchmarks show the known Phase 2 failures, unchanged.

**Tests** (`tests/test_importers.py`, `test_validation.py`, `test_export.py`)
- A wrong-type, oversized or broken file is rejected and nothing is stored.
- The mA → A conversion is correct.
- Exports never contain a non-citable dataset.
- A 50 MB file parses in ≤ 15 s (PER-7).

**Exit gate**
- [x] Tests pass. (Phase 8: 30 unit tests and 4 screen tests; full-suite count in BUILDING_JOURNEY.md.)
- [ ] The sample files from the supervisor (once received) import and validate. **Open: no sample files received yet (Round 3 Q8 promised one of each).**
- [x] Measured data stay private: `data/measured/` and the database are gitignored (tested), files are read-only, non-citable data never leave in an export (SEC-3 test), and the server listens on this computer only (SEC-1).

**Commit:** `Phase 8: measured-data import, validation report, export with citation filter`

---

## Phase 9 — AI: datasets, training / evaluation framework and registry

**Goal:** the foundation every AI feature stands on. It provides honest datasets, fair baselines, reproducible training and a record of every model (Core Module 2.5; screen M16).

**Build**
- Install scikit-learn, XGBoost, SHAP, MAPIE and MLflow, then re-pin `requirements.txt`.
- `ai/datasets.py`: generates labelled datasets by running the twin across the operating envelope.
  - Stage 1: power, pressure, flow and mixture → spectra, probe curves, T_e, n_e and T_gas.
  - Stage 2: pulse settings, gap, O₂ flow and time → species and log reduction.
- Noise levels (instrument noise, probe noise, calibration drift) are fixed from physical reasoning and written in `config/ai_datasets.toml` **before** any model is trained. The seed is recorded and these values are never tuned after seeing accuracy.
- Splits:
  - A random split, for interpolation.
  - A **region-based split** that holds out a whole corner of the envelope, to test extrapolation.
- Fault injection for anomaly detection, with each fault labelled:
  - probe tip contamination (distorted I-V);
  - spectrometer wavelength shift;
  - an air leak (unexpected N₂/O lines);
  - power-meter miscalibration;
  - RF compensation failure.
- `ai/registry.py`:
  - Logs every training run (data version, seed, hyperparameters, metrics) with MLflow in a local `mlruns/` folder.
  - Writes a model card.
  - Stamps each model with the twin version. A model trained on an older twin version is flagged as out of date (event: AI model missing or out of date).
- Baseline models, kept for comparison: ridge regression on line ratios, and a simple range check for anomalies.
- Streamlit page M16, AI training and evaluation:
  - Researchers can start training.
  - Everyone can see the metrics and model cards.

**Rules** (fixed 4 November 2026, before any Phase 9 code)
- **Libraries, as installed on Python 3.14:** scikit-learn 1.9.1, XGBoost 3.4.1, SHAP 0.54.1, MAPIE 1.6.0 and **mlflow-skinny** 3.18.0, all re-pinned in `requirements.txt`.
  - **Why mlflow-skinny:** it is the same tracking library without the web server and its database stack, which we don't need: M16 is the interface.
  - **Store:** MLflow 3.18 put the folder store into maintenance mode, and its SQLite store needs the full server stack. So the registry uses the folder store under `mlruns/` (gitignored), opting in with `MLFLOW_ALLOW_FILE_STORE=true`. That is the "local file store" SI-7 asks for.
- **Twin version (AIQ-6, E22):**
  - A new constant `plasma_twin.TWIN_VERSION` names the physics version. It is separate from the software version, which changes every phase.
  - It changes only when the twin's physics or reference data change, and every dataset and model is stamped with it.
  - A model stamped with another twin version is "out of date": it is listed, but never used.
- **Datasets (AIQ-5, CON-10):**
  - **Settings:** every sampling, noise, fault and split setting lives in `plasma_twin/config/ai_datasets.toml`. That file was locked on 4 November 2026, before any model was trained, and is committed with these rules.
  - **Dataset ID:** a hash of that file's contents, the twin version and the stage, so a changed setting gives a new ID and never silently replaces the old one.
  - **Same seed, same dataset:** identical rows.
- **Stage 1 rows:**
  - **Sampling:** a Latin hypercube over power, pressure and Ar flow (envelope ranges); the mixture is drawn equally from the four modes, with admixtures 1–10 %.
  - **Labels:** T_e, centre n_e and T_gas.
  - **OES features:** the areas of the CR-model Ar I lines in 690–860 nm, measured exactly as on M5 (`integrated_intensities`). The spectrum they are measured on is synthetic and has the locked 1 % noise and a random linear calibration tilt of up to ±5 %.
  - **Probe features:** the full noisy I–V curve (envelope default sweep, 1 % noise).
  - **Recorded:** the inputs and the seed of every row.
- **Stage 2 rows:** a Latin hypercube over the continuous inputs, plus the gap and bubble gas drawn equally. Each row stores the final O₃, H₂O₂ and OH, the log reduction, T_e, n_e and the temperature rise.
- **Faults (AIQ-2):**
  - **Which runs:** half of the Stage 1 runs carry exactly one fault, the five types equally. The magnitude is drawn from the locked range, and the fault type and magnitude are stored as labels.
  - **How each fault is made:**
    - **probe tip contamination:** the probe voltage is shifted by I·R, a series resistance;
    - **spectrometer wavelength shift:** the whole wavelength axis is offset;
    - **air leak:** the twin is run with air added (78 % N₂, 21 % O₂) but the row records the leak-free inputs;
    - **power-meter miscalibration:** the twin runs at P(1 + e) while P is recorded;
    - **RF compensation failure:** the probe curve is made with an RF residual.
  - **Rule:** every fault is made by the twin or the instrument model, never by editing labels.
- **Splits (FR16.3):**
  - **Random:** 80/20, seeded.
  - **Region:** holds out the corner P ≥ 80 W and p ≥ 0.4 mbar (Stage 1), or P ≥ 80 W and O₂ ≥ 250 sccm (Stage 2). No row inside the corner is in that split's training set.
  - **Reporting:** both results are always reported.
- **Storage:** datasets are generated, not hand-made, so the Parquet files go to `data/ai/` (gitignored; they can be rebuilt from the config and seed). A small JSON card with the dataset ID, twin version, row counts per stage and fault, seed and lock date is kept with each.
- **Registry (`ai/registry.py`, FR16.4, FR16.5):**
  - **Logging:** every training run is logged with MLflow: dataset ID, twin version, seed, algorithm, hyperparameters and metrics on both splits, for the model and its baseline.
  - **Saving:** the fitted model is saved under `models/<model_id>/` with a JSON model card.
  - **Never measured data:** models are trained on twin data only (AIQ-5). The training code cannot read the measured-data store.
- **Baselines, always trained alongside:** ridge regression on log line ratios (each line over the strongest) for T_e and n_e, and a range check for anomalies (flag a run if any feature lies outside the training range).
- **Metrics:**
  - **Regression:** MAE, median relative error and R².
  - **Anomaly detection:** recall and false-alarm rate.
  - **Model vs baseline:** a paired bootstrap of absolute errors (seeded, 2,000 resamples) gives the p-value AIQ-1 asks for.
  - Results are reported as they come, never tuned on the test set.
- **M16:** everyone sees the dataset cards, registry, model cards and logged runs; only a Researcher can start training (E23).
- **Exit gate:** the dataset settings and seed are committed (this commit) before Phase 10 starts.

**As built (4 November 2026)**
- **Code:**
  - `plasma_twin/ai/`: `datasets.py`, `registry.py` and `training.py`.
  - `scripts/build_ai_datasets.py`.
  - Screen `app/pages/11_AI_training.py` (M16).
  - Home shows the AI model status (FR1.5) and an AI entry point.
  - `TWIN_VERSION = "1.0"`.
- **Datasets built from the locked settings:**
  - **Stage 1** `S1-b898643fad`: 1,200 rows (600 clean, 120 of each fault type), in about 3 minutes on 10 processes.
  - **Stage 2** `S2-a2eb665287`: 1,500 rows in 49 s.
  - **Speed:** each row has its own seeded generator, so the build runs in parallel and still gives identical rows (tested). Reusing the fixed NIST line list removed a second CR-model solve per row.
- **Baselines on the full Stage 1 dataset, reported as they came** (the bar Phases 10 and 11 must beat):
  - **Ridge on log line ratios:**
    - random split (120 clean test runs): T_e MAE 0.104 eV (median 2.9 %), n_e median error 8.3 %;
    - region split (34 runs): T_e median 2.6 %, n_e median 8.3 %;
    - R² for T_e is low (0.32 random, negative in the corner) because T_e varies little across the envelope (about 3.0–3.4 eV), so R² is a poor measure here. MAE and median error are the ones to read.
  - **Range check:**
    - random split: recall 74 %, false alarms 36 %;
    - region split: recall 91 %, false alarms 47 %;
    - far from AIQ-2 (≥ 90 % recall at ≤ 5 % false alarms).
  - **XGBoost was deliberately not trained on the full data:** it is Phase 10's model, and its rules should be fixed before its accuracy is seen.
- **Known limits of the features, recorded:**
  - **Air leak:** the OES window (690–860 nm) holds argon lines only, because O I lines are not modelled (pending e–O data, Phase 7). So an air leak shows only through argon line ratios and the probe curve, not as new N₂ or O lines as the plan imagined.
  - **Stage 2 log reduction:** most rows reach the one-cell cap, so it carries little information; the ozone and H₂O₂ columns carry more.
- **Fixed while building:**
  - **JSON error:** the ridge run's error arrays were left in the metrics, so the card could not be saved as JSON.
  - **Process crash in tests:** a process pool started after Streamlit's AppTest crashes on Windows, so that screen test builds its 30 rows in one process.
  - **Movable folders:** `PLASMA_TWIN_MODELS` and `PLASMA_TWIN_AI_DATA` move the AI folders for tests, as `PLASMA_TWIN_DB` moves the database.
- **Storage:** `models/*` is gitignored like `data/ai/` and `mlruns/`. Models and datasets are rebuilt from the locked settings and seeds.

**Tests** (`tests/test_ai_datasets.py`, `tests/test_ai_registry.py`)
- The same seed gives an identical dataset.
- Every row is inside the envelope.
- The region split really excludes the held-out region.
- Each injected fault changes the data in the intended way.
- A model stamped with an old twin version is reported as out of date.

**Exit gate**
- [x] Tests pass. (Phase 9: 18 unit tests and 2 screen tests; full-suite count in BUILDING_JOURNEY.md.)
- [x] The dataset generation settings and seed are committed **before** Phase 10 starts. (Commit cd8e3f0, before any AI code.)

**Commit:** `Phase 9: AI datasets from the twin, baselines, MLflow registry, model cards`

---

## Phase 10 — AI: spectrum → plasma parameters

**Goal:** read T_e, n_e and T_gas directly from an emission spectrum with honest uncertainty (Core Module 2.1; screen M12).

**Build**
- `ai/inference.py`:
  - Features: a resampled, normalised spectrum and selected line ratios.
  - Models: Random Forest and XGBoost regressors (tree ensembles, no deep learning).
  - 90 % prediction intervals from MAPIE conformal prediction.
  - A training-range check: outside the range, the estimate is withheld.
- Comparison with the ridge baseline and with the physics line-ratio result from Phase 4. Significance is tested with a paired bootstrap of the absolute errors using `scipy.stats`.
- Page M12: the AI estimate always sits next to the physics analysis, and it works on synthetic and imported spectra.

**Rules** (fixed 5 November 2026, before any Phase 10 code and before any Random Forest or XGBoost accuracy on the full dataset was seen)
- **Data:** the locked Stage 1 dataset `S1-b898643fad`, clean runs only (the faulty runs belong to Phase 12). No new dataset and no changed setting.
- **Features: log line ratios, not a resampled spectrum** (a change from the plan, with its reasons):
  - **What:** log10(area / strongest area) of the 20 CR-model Ar I lines in 690–860 nm, measured with `integrated_intensities` exactly as on M5. These are the ridge baseline's features, so the comparison tests the algorithm alone.
  - **Why not a resampled spectrum:** a line's area does not change when the instrument broadens it, but its shape does. A model trained on 0.005 nm spectra would misread a measured spectrum taken at 0.05 nm, and M12 must work on imported spectra.
  - **Also:** the locked dataset stores line areas. Storing spectra would need a new dataset after the lock.
- **Targets:** T_e (eV), log10 n_e (n_e spans an order of magnitude) and T_gas (K). One regressor per target.
- **Models:** hyperparameters are fixed here and never tuned on a test set.
  - **Random Forest:** scikit-learn, 500 trees, otherwise the library defaults, seeded.
  - **XGBoost:** the Phase 9 parameters (400 trees, depth 4, learning rate 0.05, subsample 0.9, column sample 0.9).
- **90 % intervals (MAPIE split conformal):**
  - **Method:** `SplitConformalRegressor`, absolute-residual score, confidence 0.90, on a model fitted beforehand.
  - **Data:** each split's training rows are divided 75/25 (seed 20261109) into a fitting part and a calibration part. The model learns only from the fitting part.
  - **n_e:** the interval is made on log10 n_e, so it is multiplicative (for example ×0.8 to ×1.25).
  - **Fairness:** the ridge baseline still learns from all the training rows. That handicap works against the AI, not for it.
- **Training-range check (withheld estimates):** an estimate is withheld, with the reason shown, if:
  - any of the 20 lines lies outside the spectrum's wavelength range or cannot be measured (for example, blended at a wide instrument width); or
  - any feature lies outside [min − 0.1 w, max + 0.1 w] of the fitting rows, where w = max − min.

  Metrics are computed on **all** held-out rows (the check cannot flatter them), and the share that would be withheld is reported next to them.
- **T_gas:**
  - **The problem:** the 690–860 nm window holds no direct T_gas physics, because the Doppler width (about 0.0015 nm) is below the 0.005 nm instrument.
  - **The test:** the AI's T_gas is compared with a "training mean" baseline by the paired bootstrap.
  - **The rule:** if p ≥ 0.05 on the random split, M12 withholds the AI T_gas and points to the physics routes (Doppler width, N₂ rotational band).
- **Comparisons, on both splits:**
  - **(a)** against the ridge baseline;
  - **(b)** against the Phase 4 physics line-ratio fit (`fit_te_ne`), given the run's known gas density, T_gas, EEDF, geometry and quenching, and no probe. The physics fit is given more information than the AI (it knows the pressure and mixture), and this is stated wherever it is shown.
- **Significance tests:**
  - **p-values:** the Phase 9 paired bootstrap of absolute errors (T_e in eV; n_e as |Δ log10 n_e|; seed 20261108, 2,000 resamples).
  - **Confidence interval:** `scipy.stats.bootstrap` (paired, 2,000 resamples, the same seed) gives a 95 % interval of the mean error difference.
- **Physics cache:** the physics fit takes about 2 s per spectrum. It is run once per dataset on the clean held-out rows of both splits, in parallel, and cached as `data/ai/<dataset_id>-physics.parquet` (gitignored with the dataset).
- **Pass marks (tests):** each result is reported whatever it is.
  - **Coverage:** ≥ 85 % on the random split, for T_e and for n_e.
  - **Region coverage:** reported, not tested. The conformal guarantee needs held-out data like the calibration data, and the held-out corner breaks that on purpose.
  - **Significance:** model vs ridge, p < 0.05 on the random split.
- **Registry and M16:**
  - **Task and algorithms:** new task `spectrum_to_plasma` with algorithms `random_forest` and `xgboost`.
  - **Model card:** coverage, median interval widths, withheld share, and p-values and confidence intervals against the ridge baseline and the physics fit, for both splits. Everything is logged in MLflow.
- **M12 (AI spectrum analysis):**
  - **Sources:** the synthetic spectrum of the open plasma, or (for a Researcher) a measured Stage 1 OES file. Measured data are used for inference only, never for training (AIQ-5).
  - **Physics alongside:** the physics line-ratio fit is always shown next to the AI estimate.
  - **Labels:** every AI value is labelled "AI estimate" and carries its 90 % interval.
  - **When there is no current model:** if the model is missing or out of date, only the physics is shown (E22).

**As built (5 November 2026)**
- **Code:**
  - `plasma_twin/ai/inference.py`: conformal models, the range check, the physics comparison, `estimate()` and `train()`.
  - `scripts/train_spectrum_models.py`.
  - Screen `app/pages/12_AI_spectrum.py` (M12), with a Home entry point.
  - M16 now shows interval bars, the physics points (hidden until clicked in the legend), log axes for n_e, and a table of every comparison with its p-value and 95 % interval.
  - The registry logs every number on the card, including the physics comparison, to MLflow.
  - Version 0.10.0.
- **Results on the locked dataset, reported as they came** (random split: 120 clean held-out runs; region split: 34):

  | | Random Forest | XGBoost | Ridge baseline | Physics fit |
  |---|---|---|---|---|
  | T_e MAE, random (eV) | 0.104 | 0.104 | 0.104 | 0.843 |
  | T_e median error, random | 3.0 % | 2.7 % | 2.9 % | 8.1 % |
  | n_e median error, random | 9.7 % | 9.1 % | 8.3 % | 32 % |
  | T_e MAE, region (eV) | 0.094 | 0.074 | 0.085 | 0.415 |
  | n_e median error, region | 15.2 % | 11.4 % | 8.3 % | 29 % |
  | 90 % coverage T_e / n_e, random | **84 %** / 92 % | **80 %** / 89 % | – | – |
  | 90 % coverage T_e / n_e, region | 91 % / 74 % | 97 % / 85 % | – | – |
  | Median interval: T_e width / n_e factor | 0.38 eV / ×1.39 | 0.35 eV / ×1.33 | – | – |
  | p (T_e better than ridge), random | **0.49** | **0.51** | – | – |
  | p (T_e better than physics), random | 0.0005 | 0.0005 | – | – |
  | Withheld by the range check, random | 1 % | 1 % | – | – |

- **What the results say:**
  - **Trees vs ridge:** neither tree ensemble beats the ridge baseline; the ridge is even a little better for n_e. With line-ratio features, the link to T_e and log n_e is close to linear across the envelope, so a straight line is as good as a forest. **The plan's "significantly better than the baseline" is not met.** The test stays in the suite, marked as an expected failure with the measured p-values.
  - **T_e coverage below the 85 % pass mark on the locked random split:** 84 % (Random Forest) and 80 % (XGBoost). n_e passes (92 %, 89 %).
    - **A diagnostic, run after the result and changing nothing:** 30 other random splits gave a mean T_e coverage of 90.2 % (range 82–98 %), with 10 % of splits below 85 %. So the method is sound and the locked split falls in its unlucky tail.
    - The pass mark is not met, and that test is also kept as an expected failure.
  - **Region (extrapolation):** T_e coverage holds (91 %, 97 %), but n_e coverage drops (74 %, 85 %) and the n_e error grows, as expected outside the training corner.
  - **AI and ridge vs the physics fit:** both beat the Phase 4 physics fit by far (p = 0.0005), although the physics fit knows the pressure and mixture.
    - **Why the physics fit loses:** a quarter of its fits run away to 6–9 eV at low pressure.
    - **Not the cause:** the calibration tilt (correlation −0.08).
    - **The likely cause:** with both T_e and n_e free, the fit trades one against the other, which is why M5 fixes n_e from the probe (Q2, Q9).
    - **Status:** recorded as an open finding for the physics side, not changed here.
  - **T_gas** beats the training-mean baseline (p = 0.0005; MAE 0.6 K over a 300–308 K spread), so M12 shows it. It is learned from how gas heating goes with the line pattern, not from a line width, and M12 says so.
- **Added while building:**
  - **Untrained settings warning:** M12 warns when the open plasma's EEDF, spatial model or geometry differ from the settings the training runs held fixed. The line-ratio range check might not notice that kind of extrapolation.
  - **Zero-spread bootstrap:** identical error arrays give no spread, and the BCa bootstrap then returns NaN, so that case returns the single difference.

**Tests** (`tests/test_ai_inference.py`)
- On held-out synthetic spectra, interval coverage is ≥ 85 %.
- The ensemble's error is significantly lower than the baseline's (p < 0.05). Whatever the result, it is reported honestly.
- Results are reported separately for the random split and the region split.
- Out-of-range input is withheld.
- One inference takes ≤ 1 s.

**Exit gate**
- [x] Tests pass, with two results recorded as expected failures (strict). Both tests stay in the suite with their measured values:
  - T_e coverage on the locked random split: 84 % / 80 %;
  - the trees are not significantly better than the ridge: p = 0.49 / 0.51.

  n_e coverage, the region and physics comparisons, the range check and the ≤ 1 s inference (0.19 s on M12) pass.
- [x] Coverage and the baseline and physics comparisons are recorded in MLflow and on M16 (and summarised on M12).

**Commit:** `Phase 10: AI spectrum-to-parameter inference with conformal intervals`

---

## Phase 11 — AI: surrogate model and explainability

**Goal:** a fast learned copy of the twin for large explorations, with SHAP explaining which inputs drive each output (Core Module 2.3; screen M15).

**Build**
- `ai/surrogate.py`: XGBoost / Random Forest surrogates.
  - Stage 1: power, pressure, flow and mixture → T_e, n_e, T_gas and key line intensities.
  - Stage 2: pulse settings, gap, O₂ flow and time → log reduction and species.
- SHAP gives global importance (which inputs matter most overall) and local explanations (why this run gave this value).
- Every surrogate value is labelled "surrogate". Any number used for a decision is re-checked with the twin, and if the two disagree by more than the tolerance, the twin value is shown (event: surrogate–twin disagreement).
- Page M15: fast sweep heatmaps, SHAP plots, and a "check with twin" button.

**Rules** (fixed 6 November 2026, before any Phase 11 code and before any surrogate was trained)
- **What the surrogate copies:** the twin's own noise-free outputs, not instrument readings. A surrogate copies the twin, so spectrometer noise and calibration tilt do not belong in its targets.
  - **Stage 1:** the locked dataset stores noisy line areas, and its faulty rows' recorded inputs do not match their plasma. So the twin is re-run, noise-free, at the 1,200 recorded inputs of the locked Stage 1 plan (same seed, same rows, no faults). The outputs are cached as `data/ai/<dataset_id>-twin.parquet` (gitignored). No locked setting changes.
  - **Stage 2:** the locked dataset is already noise-free, so its 1,500 rows are used as they are.
- **Inputs:** every other setting is held at its default, and M15 warns when the open configuration differs in one of them.
  - **Stage 1:** power, pressure, Ar flow, N₂ % and O₂ % (0 when the gas is absent, so they also encode the mixture). Held at defaults: EEDF (Druyvesteyn), 0D, geometry.
  - **Stage 2:** power, frequency, pulse width, O₂ flow, water temperature, treatment time, water volume, pH, power share, gap, and water vapour (1 if the bubble gas holds it). Held at defaults: voltage, conductivity, COD, waste type, organism, initial count.
- **Outputs and the scale each is learned on:**
  - **Stage 1:** T_e (eV), log10 n_e, T_gas (K), and log10 of the noise-free emission of the four strongest lines in the window: 763.5, 811.5, 750.4 and 842.5 nm.
  - **Stage 2:**
    - T_e (eV);
    - log10 n_e, log10 O₃ and log10 temperature rise;
    - log10(H₂O₂ + 1e-9 mmol/L) and log10(OH + 1e-20 mol/L). The floors are about 1,000 times below the smallest non-zero value, because these are exactly zero in many "O₂ only" runs;
    - log reduction.
- **Models:** hyperparameters are fixed here and never tuned on a test set.
  - **XGBoost:** one multi-output model per stage (one tree per output per round, the Phase 9 parameters). One call predicts every output, which matters for speed. It is the surrogate M15 uses by default.
  - **Random Forest:** offered for comparison (500 trees, scikit-learn's multi-output forest) and reported.
  - **Baseline:** a ridge regression on the standardised inputs, per output, reported beside them.
- **Splits:** the Phase 9 random and region splits for each stage. Both are always reported.
- **Accuracy metrics, per output:**
  - **R²:** on the scale the output is learned on (log10 for the wide-range outputs). In linear units a few of the largest values would decide it.
  - **Median relative error:** in the original units, over held-out rows whose true value is not zero.
  - **Mean absolute error:** in the original units.
- **Speed (AIQ-3):**
  - **The twin's time:** the median wall-clock time of one twin run over 20 held-out configurations, run one after another. Stage 1 is the global model plus the CR model (needed for the line outputs). Stage 2 is the bubble, liquid and survival chain.
  - **Pass mark:** speed-up per configuration inside a 625-point map (25 × 25, one call), which is what M15 does.
  - **Also reported:** the speed-up of a single one-configuration call.
  - **Pre-check, recorded honestly:** on synthetic data a single XGBoost call costs 2–4 ms of fixed overhead, so the single-call speed-up for Stage 2 (twin ≈ 0.2 s) may fall below 100×. That is why the pass mark is set on the map use, and the single-call figure is reported beside it.
- **SHAP:**
  - **Method:** TreeExplainer on the trained model, on each output's learned scale.
  - **Global importance:** the mean |SHAP| over the random split's held-out rows, stored on the model card.
  - **Local:** computed on M15 for the open configuration; local values must add up to the prediction minus the expected value.
- **Twin check (FR15.3, FR17.22, E27):**
  - **When the two disagree:** if |surrogate − twin| > 5 % of |twin| (`surrogate_twin_disagreement_percent` in envelope.toml), the twin value is the one shown and the point is flagged on the map.
  - **Zero outputs:** an output whose twin value is zero counts as agreeing if the surrogate is within its floor.
- **Pass marks (tests, XGBoost, random split):** each result is reported whatever it is.
  - **Accuracy:** every output of both stages reaches R² ≥ 0.98 and median relative error ≤ 5 %.
  - **Speed:** at least 100× per configuration in a map, for each stage.
  - **SHAP additivity:** SHAP values add up to the prediction minus the expected value (to 1e-3).
  - **Physical sense:** for Stage 1 T_e, mean |SHAP| of pressure exceeds that of power.
  - **Region split:** reported, not tested.
- **Known in advance, recorded so the numbers are read correctly:**
  - **Stage 2 log reduction:** every Stage 2 row reaches the one-cell cap, so log reduction follows the water volume exactly. Its surrogate score says nothing about kill kinetics.
  - **T_gas:** its relative error is small by construction (300–308 K), so its R² is the meaningful measure.
- **Registry and M15/M16:**
  - **Tasks:** `surrogate_stage1` and `surrogate_stage2`, algorithms `xgboost` and `random_forest`.
  - **The card:** per-output metrics on both splits, the ridge baseline, both speed-ups, and the global SHAP importance.
  - **Labels:** M15 labels every surrogate value "surrogate".

**Tests** (`tests/test_ai_surrogate.py`)
- On held-out twin runs: R² ≥ 0.98 and median relative error ≤ 5 %.
- The surrogate is at least 100× faster than the twin.
- SHAP values for one prediction add up to that prediction minus the baseline value.
- Physical sense check: SHAP ranks pressure above power for T_e, because the particle balance makes T_e depend on pressure, not power.

**Exit gate**
- [ ] Tests pass.
- [ ] The accuracy and speed-up numbers are recorded.

**Commit:** `Phase 11: AI surrogate of the twin with SHAP explanations`

---

## Phase 12 — AI: physics-relationship anomaly detection

**Goal:** flag runs and measured files whose diagnostics break the expected physics relationship, which a simple range check cannot catch (Core Module 2.2; screen M13).

**Build**
- `ai/anomaly.py`:
  - Features are **residuals** between the twin's prediction and the observation: OES T_e vs model, probe n_e vs model, line-ratio residuals, and I-V shape residuals.
  - An Isolation Forest is trained on normal twin runs with realistic noise.
  - Severity levels are Normal, Warning and Critical, and the residual that contributed most is named as the likely cause.
- Applied to saved sessions and to imported measured files (from Phase 8).
- Page M13: an anomaly list, a severity timeline, and the likely-cause panel.

**Tests** (`tests/test_ai_anomaly.py`)
- On held-out injected faults: recall ≥ 90 % at a false-alarm rate ≤ 5 %.
- Recall is significantly higher than the range-check baseline. A fault with all values in range but the physics broken must be caught.
- Clean runs are rated Normal.

**Exit gate**
- [ ] Tests pass.
- [ ] A per-fault-type detection table is recorded.

**Commit:** `Phase 12: AI physics-relationship anomaly detection`

---

## Phase 13 — AI: counterfactual recommendations (inverse design)

**Goal:** the user states a goal and the AI proposes settings to reach it. **Every proposal is re-simulated through the twin** and its real predicted outcome is reported, never just advisory text (Core Module 2.4; screen M14).

**Build**
- `ai/recommend.py`:
  - Example targets:
    - Stage 2: at least 3-log *E. coli* reduction with the least energy per litre.
    - Stage 1: a target n_e or T_gas, or the strongest Ar 750 nm line.
  - Constraints are the operating envelope and any fixed settings.
  - Search on the surrogate (Phase 11) with `scipy.optimize.differential_evolution`, then keep the top 3 candidates.
  - Each candidate is re-run through the twin, which reports the predicted outcome, the distance to the target and the energy used.
  - What-if counterfactuals: "change X by Δ, and the twin predicts …".
  - If no setting inside the envelope reaches the target, say so and show the closest one (event: target unreachable).
- Page M14: a target form, ranked candidates, twin-verified outcomes, and "apply to configuration".

**Tests** (`tests/test_ai_recommend.py`)
- 100 % of recommendations carry a twin-verified outcome.
- On a benchmark set of targets, the twin confirms the target is met within tolerance for ≥ 90 % of them.
- An impossible target is reported as unreachable.
- A recommendation takes ≤ 60 s.

**Exit gate**
- [ ] Tests pass.
- [ ] No recommendation is ever shown without its twin re-simulation.

**Commit:** `Phase 13: AI counterfactual recommendations verified by the twin`

---

## Phase 14 — Final test pass and report

**Goal:** prove every requirement of both core modules and write the report.

**Build / check**
- Domain-layer coverage is ≥ 80 % for both `plasma_twin/` physics and `plasma_twin/ai/` (MNT-1).
- Every public function has type hints and a docstring explaining the physics or statistics reason (MNT-3).
- Time every performance target on the reference laptop.
- Check that every backend event produces its message.
- Fill in:
  - the physics validation tables (±30 %);
  - the AI quality tables: coverage, baseline significance, anomaly recall and false-alarm rate, surrogate R² and speed-up, recommendation success rate.

  Report failing results honestly.
- Update the SRS and scope document if anything changed (new revision-history row), write the final report, and prepare the demo and viva.

**Exit gate**
- [ ] All tests pass.
- [ ] Every FR is ticked off.
- [ ] Every NFR and AI-quality target is measured and recorded.

**Commit:** `Phase 14: full test pass, NFR and AI-quality measurements, final report`

---

## Open items to settle before the phase that needs them

| Item | Needed by | Source |
|---|---|---|
| Are N₂ and O₂ added in the same run? Is "5 %" of the Ar flow? | Phase 3 | Supervisor (UNDERSTANDING.md §8, item 1) |
| Published time-resolved *E. coli* survival data for the Hom fit | Phase 7 | Literature search |
| Pulse width (100 µs at 5–10 kHz is not pulsed; we use 10 µs by default) | Phase 7 | Supervisor (§8, item 2) |
| Sample measured OES (.txt) and probe (.csv) files | Phases 8 and 12 (anomaly detection on real data) | Supervisor (promised one of each) |
| Final submission deadline | Planning | Supervisor (not answered yet) |
