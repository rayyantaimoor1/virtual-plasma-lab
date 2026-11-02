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

**4e — Gas temperature and the N₂ band** (`oes/gas_temp.py`; rules written before 4e starts)
- **Doppler:** the gas temperature from the extra width of an isolated line, enabled only when the instrument FWHM is no larger than the expected Doppler FWHM (E8). At 300 K the Doppler FWHM of an argon line near 750 nm is about 0.0015 nm, so at the default 0.005 nm it is disabled.
- **N₂ rotational temperature** from the (1,0) band at 315.9 nm, with an NH overlap check, and the N₂ second positive band in the spectrum when N₂ is present.
- **O I lines (777 and 844 nm): moved to Phase 7.** Excitation data for atomic oxygen are not in hand, and Phase 7 (underwater OES) needs them anyway. Phase 4 does not draw O I lines; changed from the original plan with this reason.

**Tests** (`tests/test_cr_model.py`, `test_spectrum.py`, `test_boltzmann.py`, `test_oes_gas_temp.py`, `test_line_ratio.py`)
- Populations are positive and increase with n_e.
- The spectrum peaks sit at the NIST wavelengths.
- A perfect Boltzmann population gives back its own temperature.
- The line-ratio T_e from a noise-free synthetic spectrum is within ±30 % of the model T_e (ACC-2).
- Doppler is disabled at 0.005 nm resolution.
- Recomputing the spectrum takes ≤ 3 s (PER-2).

**Exit gate**
- [ ] Tests pass.
- [ ] T_exc is never labelled as T_e anywhere in the outputs.

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

**Tests** (`tests/test_probe_iv.py`, `test_probe_analysis.py`, `test_eepf.py`, `test_compare.py`)
- A noise-free curve recovers the model T_e and n_e within ±10 % (ACC-2).
- The EEPF recovered from a Druyvesteyn plasma is Druyvesteyn-shaped.
- The comparison flags 31 % as a fail and 29 % as a pass.
- Generation plus analysis takes ≤ 2 s (PER-3).

**Exit gate**
- [ ] Tests pass.
- [ ] Results with O₂ present are flagged as approximate (LI-4).

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

**Tests** (`tests/test_sessions.py` plus manual checks in the app)
- Sessions survive a restart.
- Deleting a session asks for confirmation.
- Injection strings typed into notes and search do nothing.
- Each FR1.x–FR7.x requirement is checked by hand against its mockup.

**Exit gate**
- [ ] A new user runs the default experiment in ≤ 2 clicks (USE-1).
- [ ] The full M1→M7 workflow works in the browser.
- [ ] All tests pass.

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

**Tests** (`tests/test_pulse.py`, `test_bubble_model.py`, `test_liquid.py`, `test_hom.py`, `test_uw_oes.py`)
- 100 µs at 10 kHz is blocked.
- 10 µs at 5 kHz gives a duty cycle of 5 % and 20 mJ per pulse.
- The Hom model reproduces its own fitted points.
- The temperature rise equals energy ÷ (mass × specific heat).
- The Stark width inverts back to the n_e that produced it.
- One run takes ≤ 10 s (PER-5).

**Exit gate**
- [ ] Tests pass.
- [ ] The log reduction is within ±30 % of the published reference at 1 or more points (ACC-1, BO-4).

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

**Tests** (`tests/test_importers.py`, `test_validation.py`, `test_export.py`)
- A wrong-type, oversized or broken file is rejected and nothing is stored.
- The mA → A conversion is correct.
- Exports never contain a non-citable dataset.
- A 50 MB file parses in ≤ 15 s (PER-7).

**Exit gate**
- [ ] Tests pass.
- [ ] The sample files from the supervisor (once received) import and validate.
- [ ] Measured data stay private.

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

**Tests** (`tests/test_ai_datasets.py`, `tests/test_ai_registry.py`)
- The same seed gives an identical dataset.
- Every row is inside the envelope.
- The region split really excludes the held-out region.
- Each injected fault changes the data in the intended way.
- A model stamped with an old twin version is reported as out of date.

**Exit gate**
- [ ] Tests pass.
- [ ] The dataset generation settings and seed are committed **before** Phase 10 starts.

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

**Tests** (`tests/test_ai_inference.py`)
- On held-out synthetic spectra, interval coverage is ≥ 85 %.
- The ensemble's error is significantly lower than the baseline's (p < 0.05). Whatever the result, it is reported honestly.
- Results are reported separately for the random split and the region split.
- Out-of-range input is withheld.
- One inference takes ≤ 1 s.

**Exit gate**
- [ ] Tests pass.
- [ ] Coverage and baseline comparison are recorded in MLflow and on M16.

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
