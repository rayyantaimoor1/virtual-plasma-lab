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

**How Phase 2 closed (2 November 2026).** By team decision, Phase 2 closed with one gate item unmet: agreement with the measured n_e and T_e within ±30 %. Every other item passed. We chose not to keep adding physics while the most likely remaining cause, generator versus absorbed power, waits on the supervisor (Q3). Without his answer, each new change would risk tuning the model to the data. When Q3 is answered, the same comparison is re-run as run 4.

**Where it stands:** the model is built and well tested (145 tests pass, plus the gate test marked as an expected failure), and the trends match the measurements. The ±30 % gate is not met. All three runs are recorded in `docs/validation/phase2_stage1_benchmarks.md`.

---

## Phase 3: Stage 1 extensions (complete, 3 November 2026)

**What we made**
- **3a, gas flow (`gas_flow.py`):** converts sccm to atoms per second, works out the residence time in the 40 × 40 cm chamber, and adds pumping as a loss for excited atoms.
- **3b, gas temperature (`gas_temperature.py`):** T_gas is now an output of a heat balance, and the model is re-solved until it settles. It gives about 301–304 K over 10–100 W.
- **3c, axial profile (`profile1d.py`):** the n_e profile between the electrodes. It is the cosine solution of ambipolar diffusion, pinned to the 0D centre and sheath-edge densities.
- **3d, sweeps (`sweep.py`):** up to 200 points. A failed point is kept with its reason; 200 points take about 66 s, inside the 120 s limit (PER-4).
- **Data:** argon thermal conductivity, 300–1000 K, from the NIST WebBook, with checksum and citation.

**Techniques and why**
- **Switches for every new effect.** With flow and heating off, the Phase 2 results come back exactly, and the Phase 2 tests now run that model explicitly.
- **Expectations written down before building.** For example, the plan said flow would barely matter in pure argon, because pumping takes seconds and diffusion to the walls milliseconds. The result agreed: under 1 %.
- **Exact maths instead of a mesh.**
  - Heat conduction in the cylinder is solved with a Bessel–cosine series, and a test checks it against the exact slab result l²/12.
  - The Kirchhoff transform makes conduction linear even though the conductivity changes with temperature.
- **Gas heating sources chosen on physics, not on the result.** Only elastic collisions and metastable quenching heat the gas. Sheath ion energy goes to the electrodes, and pooling energy goes to electrons. So T_gas is labelled as a lower estimate.

**Problems and how we handled them**
- **I misremembered the sccm conversion** (4.46 instead of 4.48 × 10¹⁷ atoms/s). The code was right and the test was wrong. The test now checks against CODATA's Loschmidt constant, not a remembered number.
- **The Kirchhoff inversion was 6 % off for small temperature rises.** I had interpolated Φ in straight lines, but it curves because κ rises about 13 % between NIST points. Fixed by integrating the interpolated κ exactly and inverting with a root finder. A test caught it.
- **A line-number edit removed the wrong lines.** Spotted on inspection and repaired before anything was run or committed.
- **The plan's 1D test was wrong for our model.** It said "the profile's average equals the 0D n_e", but the 0D n_e is the centre density. The test now checks the centre and edge values instead, with the reason in `BUILD_STEPS.md`.

**3e, N₂ and O₂ mixtures (`mixtures.py`)**
- **What it does:** four gas modes (Ar, Ar+N₂, Ar+O₂, Ar+N₂+O₂), each admixture a percentage of the argon flow. It tracks three positive ions (Ar⁺, N₂⁺, O₂⁺), and with oxygen also O⁻, O atoms and O₂(a¹Δ). It also gives the N₂(C) excitation rate needed for the 337 nm band in Phase 4.
- **Finding the sources took most of the work.** Every rate was read in a source before the rules were written:
  - **Electron collisions with N₂ and O₂:** the Biagi cross-sections we already had, integrated with the chosen EEDF, so they stay consistent with argon.
  - **Charge transfer:** Anicich's evaluated compilation (NIST-hosted reprint), giving Ar⁺ + N₂ and Ar⁺ + O₂.
  - **Argon metastables quenched by N₂:** two arXiv papers citing Le Calvé & Bourène (1973) and Pothiraja et al. (2010).
  - **Oxygen chemistry and quenching by O₂:** a 2026 arXiv CCP Ar/O₂ global model (Dong et al.) and Kemaneci et al. (2016).
  - **Electron affinity of O:** NIST WebBook.
  - Several sources were blocked (Wiley, a thesis server, a human-verification check). We never took a number from a search summary.
- **Choices flagged in writing before coding:**
  - One source row (O⁻ + Ar⁺ recombination, 2.7×10⁻¹⁷) looks like a misprint. We did not "correct" it from memory; the analogous O₂⁺ + O⁻ value stands in for every positive ion.
  - One quenching rate is faster than a gas-kinetic collision would suggest. It is kept as published and flagged.
  - N₂ dissociation, O₃, NO and O₂(b) are left out, with reasons.
- **Solver:** the 9–13 unknowns are solved together by stepping the admixture up from 0.1 % to 100 % of its value, starting from the pure-argon answer. A full run with gas heating takes under 1 s.

**Problems in 3e and how we handled them**
- **A naming mismatch** (`to_o2a` against `to_o2_a`) stopped every oxygen run. It was found at the first try and fixed.
- **The model said adding O₂ raises n_e** (2.6 times higher at 1 % O₂), the opposite of the measured trend in Ar/O₂ CCPs. We treated this as a model fault, not a result.
  - **Diagnosis:** the electronegative Bohm factor came out at 0.32 for only α = 0.087. Our rule had put the centre electronegativity into Kemaneci's Eq. 14. But their Eq. 11 defines it at the sheath edge, and Boltzmann negative ions (γ = T_e/T_g ≈ 110) are pushed almost entirely out of the edge.
  - **Fix:** use α_s = α₀ (n_e,edge/n_e,centre)^(γ−1), following the source's own definition. n_e now falls as O₂ is added (3.2 → 2.6 × 10¹⁶ m⁻³ at 5 %).
  - **Why this is not tuning:** the change was justified by the source, made before any comparison with measured data, and recorded in `BUILD_STEPS.md` as a change from the rule.
- **Plan versus build:** the plan said 3e-1 (N₂) and 3e-2 (O₂) would be committed separately. Both ended up in one module, so they were committed together, after argon + N₂ had been run and checked alone first.

**What the mixtures show (at the defaults, 50 W and 0.3 mbar, gas heating off)**
- **5 % N₂:** n_e falls from 3.2 to 2.5 × 10¹⁶ m⁻³, because N₂ absorbs electron energy; excitation rises from 22 % to 36 % of the power. Metastables fall to 60 %. N₂⁺ makes about 14 % of the positive ions.
- **5 % O₂:** n_e falls to 2.6 × 10¹⁶ m⁻³, and the plasma becomes electronegative (α ≈ 0.5). About a third of the oxygen is dissociated into atoms. Metastables drop about fifteenfold, because O₂ quenches them very fast.

**How Phase 3 closed:** all three exit-gate items are met: 195 tests pass; with the new effects switched off, the Phase 2 argon results are reproduced exactly; and this section is written. The Phase 2 benchmark gap is still open and still waits on supervisor question Q3.

---

## Phase 4: virtual OES (complete, 3 November 2026)

**What we made**
- **4a, CR model (`oes/cr_model.py`):** the populations of the four argon 1s and ten 2p levels from the plasma state, and from them 29 emission lines (2p → 1s), including radiation trapping.
- **4b, spectrum (`oes/spectrum.py`):** the lines as a spectrometer would record them, with instrument width, Doppler width, an area-true line shape and seeded noise. A full 300–900 nm spectrum takes under 1 s.
- **4c, Boltzmann plot (`oes/boltzmann.py`):** the excitation temperature with its error and R², and the E9 reliability rule.
- **4d, line-ratio T_e (`oes/line_ratio.py`):** the CR model run backwards to fit T_e and n_e to the line pattern.
- **4e, gas temperature (`oes/n2_band.py`, `oes/gas_temp.py`):** the N₂ second positive bands; the N₂ rotational temperature from the (1,0) band; the Doppler temperature with the E8 rule; and an NH overlap check.

**New data:** the LXCat **BSR** database (electron collisions from each argon 1s level; downloaded with your agreement to LXCat's terms, kept local), NIST Ar I lines at 1000–1400 nm, N₂ ground-state constants, and Gilmore et al.'s (1992) N₂ band table, all with checksums and citations.

**Techniques and why**
- **Every rate from cross-sections, the reverse ones too.** De-excitation rates come from the same cross-sections through detailed balance on the cross-section (Klein–Rosseland), so they stay right for a Druyvesteyn EEDF, not only a Maxwellian.
- **Names and energies taken from the data, not from memory.** The Racah-to-Paschen mapping is read from the BSR file's own labels, and each NIST line is matched to its levels by energy within 4 meV.
- **Trapping by Mewe's escape factor,** found in an open paper (arXiv:2402.08092) that writes it out. The CCP papers that use it cite only paywalled sources.
- **Methods proven before use.**
  - The Franck–Condon factors from Morse potentials had to reproduce Gilmore's published factors within 5 % (they did, within 1–3.4 %) before being used for the excitation split.
  - The Kratzer relation was checked against two NIST values.
  - The vacuum-to-air formula was checked against NIST's argon lines.
- **Excitation temperature never called T_e:** checked by a test, and required by the exit gate.

**Problems and how we handled them**
- **The CR model's 1s5 density is about four times the global model's metastable density.** Diagnosed, not hidden: BSR destroys 1s5 ten times more slowly through 1s mixing (3.6×10⁻¹⁴ against the published lumped 3.7×10⁻¹³ m³/s). Both are reported. Switching the global model to BSR rates would change Phases 2–3, so it is left as an open decision.
- **The visible NIST file stops at 1000 nm,** but some 2p levels also decay by infrared lines (2p10 → 1s3 near 1047 nm). We added a second NIST download to 1400 nm, so every decay route is included.
- **A weak balance test** only checked that radiation was positive. It was replaced by an exact check that every level's gains equal its losses (residual < 10⁻⁹).
- **The line-ratio fit is exact without noise and about 1 % off at 1 % noise, but fails at 5 % noise.** Weak lines dominate an unweighted log fit. Uncertainty weighting is the standard fix, but it is a change of method, so it is recorded as future work.
- **The NH check gave a false alarm,** because N₂'s own (0,0) band reaches past 336 nm. It was fixed to flag only the excess beyond the N₂ prediction, and recorded as a change to the rule.
- **N₂ rotational temperature at 1 % noise:** on a full 300–900 nm acquisition it misses by 16–29 %, because the 811 nm argon line sets the noise level. On a UV acquisition it is within 0.7 %. Both are recorded, and the lesson is practical: measure T_rot with a separate UV acquisition.
- **O I lines moved to Phase 7,** where the excitation data for atomic oxygen are needed anyway.

**What the virtual OES shows at the defaults:** the brightest line is 811.5 nm, as in real argon. T_exc is about 0.5 eV with R² = 0.05, flagged unreliable, against T_e = 3.06 eV. That is the known behaviour of low-pressure argon: its 2p levels are not in equilibrium with the electrons.

**How Phase 4 closed:** all three exit-gate items are met: 245 tests pass, T_exc is never labelled T_e, and this section is written.

---

## Phase 5: virtual Langmuir probe and diagnostics comparison (complete, 3 November 2026)

**What we made**
- **`probe/iv_model.py`:** the I-V curve of the laboratory's cylindrical tungsten probe (0.195 mm × 5 mm, −20 to +50 V), computed from the model's own plasma: electron density, EEDF, ions and plasma potential. It includes OML ion current, optional RF distortion and seeded noise.
- **`probe/analysis.py` and `probe/eepf.py`:** the laboratory's analysis steps.
  - **V_f, V_p:** V_f from the zero of the current; V_p from the zero of d²I/dV².
  - **EEPF:** by the Druyvesteyn method, giving n_e and T_eff.
  - **Also:** the slope T_e, the saturation n_e, the Debye length and the OML validity check.
  - **Failures:** a failure names the step it stopped at.
- **`compare/diagnostics.py`:** model, OES and probe side by side for T_e, n_e and T_gas.
  - **Rules:** a ±30 % pass rule; dependent and unreliable values are marked and not counted; T_exc is shown but excluded.
  - **Also:** the O₂ "approximate" flag, and a list of each method's assumptions.

**Techniques and why**
- **Formulas read in the source, not remembered:** the OML ion current is Chen's Eq. 22, from his open lecture notes. Chen gives the Druyvesteyn method only as a proportionality, so we derived the exact constant from the same retarding-current integral the curve generator uses, and checked it against the textbook form.
- **The probe sees exactly the model's plasma,** so a noise-free curve must give the model's values back. That turns the probe into a test of the analysis chain before it is ever used on measured data.
- **Every new rule checked by an exact test:**
  - the Maxwellian exponential;
  - the random-flux current at V_p;
  - the Savitzky–Golay noise gain against the filter's own weights;
  - the noise estimator against white noise and against smooth curves.

**Problems and how we handled them**
- **With realistic 1 % noise the EEPF is meaningless.** T_eff came out about 200 % high, because the second derivative turns noise into a false energy tail.
  - **Tried first:** cutting the EEDF at its first zero past the peak. It failed, because the peak itself was a noise spike, so it was removed.
  - **The final answer:** a reliability flag computed from the measured noise, with the EEPF trusted only if noise could change n_e and the mean energy by at most 5 %. Plus the textbook saturation density, which stays within 6 % at 1 % noise.
  - **The lesson for the laboratory:** EEPFs need averaged sweeps or very low noise.
- **Noise broke three analysis steps.** It made false zero crossings (V_f, V_p) and a rising ion fit. Each step was made robust, and the changes are recorded in `BUILD_STEPS.md`.
- **V_p reads slightly low,** because the cylindrical electron-saturation current bends sharply just above V_p. At the laboratory's 0.5 V step this makes n_e(EEPF) 14 % low. It is recorded and pinned by a test. The ±10 % test uses a 0.1 V step, where it passes, and an exact test proves the V_p offset is the only error.
- **A false EEPF spike at 3–4 eV** came from the ion fit reaching zero too early (at 8.5 V, not at V_p = 12 V). It was fixed by refitting with OML's own condition, ion current zero at V_p.
- **My first noise estimate counted smooth misfit as noise** and flagged a noise-free curve. It was replaced by a second-difference estimator, which is blind to smooth trends.
- **A test tolerance I nearly chose after seeing the numbers** (12 %) was replaced by a test of the exact relation the offset predicts, at the same 3 % as the formula test.
- **One shell command failed on quoting**, so the test files were written directly; nothing ran half-way.

**What the comparison shows**
- **Defaults (probe noise 1 %):** the probe EEPF is flagged, so only OES T_e counts, and it misses by +34 %.
- **Noise-free probe, argon:** T_e from the probe −4 %, n_e −14 %; 1 of 2 quantities agree.
- **Noise-free probe, 5 % N₂:** all 3 quantities agree (T_e: OES +29 %, probe −3 %; n_e: probe −14 %; T_gas: +1 %).
- **A finding for the supervisor (added to Q9):** taking OES n_e from the probe makes the OES T_e very sensitive to it, about 30 % per 10 % error in n_e.

**How Phase 5 closed:** all exit-gate items are met: 280 tests pass, results with O₂ are flagged approximate and never counted, and this section is written.

---

## Phase 6: Stage 1 dashboard and sessions (complete, 3 November 2026)

**What we made**
- **Eight screens:** Home (M1), Chamber configuration (M2), Results (M3), Virtual OES (M4), OES analysis (M5), Langmuir probe (M6), Comparison (M7) and a basic Sessions list (M11).
- **Sessions:** save, list, search, open, compare (2–5) and delete with confirmation. They are stored in SQLite with IDs S-0001, S-0002, … that are never reused.
- **Five example experiments,** including the supervisor's argon + 5 % N₂ + 5 % O₂ mixture, plus a one-click quick start.

**Techniques and why**
- **Three layers.**
  - The screens (`app/`) only display things.
  - A service layer (`plasma_twin/services/stage1.py`) turns screen values into model inputs, checks them field by field, runs the model and turns results into plain JSON.
  - The physics never imports Streamlit.
  - This keeps every rule testable without a browser.
- **Safety:** every SQL statement uses placeholders, so typed text is data, never code. Six injection-style strings are tested, and the tables survive them. Deleting needs `confirmed=True`, which the screen passes only after a second click.
- **Caching:** every model, spectrum and probe run is cached by its inputs, so moving between screens never re-solves the plasma.
- **Readable charts:** every axis has a symbol and an SI unit, and every status message has words as well as colour. The 600,000-point spectrum is drawn reduced to 4,000 points, keeping every bin's peak. A test checks that no line peak is lost.
- **Tested two ways:**
  - Streamlit's own `AppTest` runs every screen headless: one-click quick start, live validation, save → list → delete.
  - The full workflow was clicked through in the built-in browser.

**Problems and how we handled them**
- **Search matched the stored configuration's field names** (a search for "_" matched every session). The first version searched the JSON with SQL LIKE. It now matches the note and the configuration values in Python, so typed text never reaches SQL.
- **The browser check found four display problems,** fixed and recorded:
  - cut-off metric values;
  - an unreliable probe value shown as if trustworthy;
  - a repeated phrase on the comparison screen;
  - a crash from mixing whole-number and decimal limits.
- **A screen crashed after editing the shared module.** The running server keeps imported modules, and a restart fixed it. It is recorded as a development note.
- **The 200-point sweep test failed once (191 s, limit 120 s).**
  - **Profiling** showed each gas-temperature repetition restarting the solver from scratch, so each now starts from the previous solution. That is a speed-up only: the answer must still close every balance to 10⁻¹¹.
  - **Measuring again** showed the real cause of the swings: the laptop was on battery and Windows throttled the CPU, with the same unchanged code up to 5 times slower within seconds. So timing tests need the laptop plugged in. With the speed-up the sweep passes even throttled (96 s).
- **A test session I saved during the browser check** was deleted afterwards, so your session database starts empty.

**Left for Phase 8,** as planned: overlaying and analysing imported measured data (FR4.6, FR5.1, FR6.9), PDF reports, and the non-citable-data rule (FR11.5).

**How Phase 6 closed:** all exit-gate items are met: one-click quick start, the M1→M7 workflow working in the browser, 315 tests passing, and this section written.
