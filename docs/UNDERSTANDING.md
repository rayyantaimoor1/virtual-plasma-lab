# Plasma Digital Twin (new direction) - Shared Understanding

**Status:** planning only. No code has been built or changed for the new direction.
**Written:** 2026-10-25, from the supervisor's questionnaire answers (Rounds 1 and 3), the student's own instructions, and a literature search.
**Purpose of this file:** one place that records everything understood so far, so it can be checked, corrected, and used as the base for the new scope document and build.

Conventions used below:
- **[SUP]** = stated by the supervisor in a questionnaire. These are authoritative.
- **[STU]** = stated by the student (Rayyan) in chat.
- **[LIT]** = taken from a published paper or web source (used only where the supervisor left a point blank or unclear).
- **[MINE]** = my interpretation or proposal. These need confirming.

---

## 1. People and project

| Item | Value |
|---|---|
| Project | AI-Assisted Plasma Process Experimentation & Digital Twin Analytics Platform (Final Year Project, BSCS 2023-2027, COMSATS University Islamabad) |
| Students | Muhammad Rayyan Taimoor Khan (CIIT/FA23-BCS-072/ISB) - Digital Twin and AI core; Sadeem Ur Rehman (CIIT/FA23-BCS-127/ISB) - Dashboard and Analytics |
| Supervisor | Dr. Majid Iqbal. The student describes the supervisor as a plasma-physics professor whose idea the project originally was. |
| Working rule [STU] | The supervisor's answers have priority. Web papers are used **only** for points he left blank or unclear. |
| Working rule [STU] | Rayyan has limited coding experience: code must be clear and well commented, with physics/statistics decisions explained, and both students must be able to defend every part. |

---

## 2. What existed before (the old project, in `plasma-digital-twin/`)

A complete, tested software-only virtual plasma lab for a **low-pressure RF capacitively coupled argon plasma** with a semiconductor-processing framing.

- **Digital twin (`digital_twin/`):** 0D (volume-averaged) global discharge model after Lieberman & Lichtenberg Ch. 10. Particle balance solved with `scipy.optimize.brentq` gives Te from pressure and geometry; power balance gives n_e. Child-Langmuir sheath when an RF voltage is supplied. Derived "indices" (reactivity, uniformity, etch rate, process quality, defect probability). Chamber config with 3 presets, SQLite sessions, sensitivity sweeps, synthetic dataset with hidden confounders (seed 20260710), and physics validation against Turner (2014) and two other K_iz sources (9 checks, **6 pass**).
- **AI module (`ai_module/`):** Random Forest and XGBoost classifiers against a logistic-regression baseline with McNemar's test (neither ensemble significantly better, reported honestly); SHAP; Isolation Forest anomaly detection on physics residuals; optional PyTorch autoencoder; trend and correlation analysis; semiconductor suitability windows; counterfactual recommendations; MLflow training registry; MAPIE conformal uncertainty.
- **Front ends:** Streamlit dashboard (8 pages) and a FastAPI + JavaScript "Reactor Control Room" companion app; three `.bat` launchers.
- **Quality:** about 383 tests reported at the last commit; GitHub Actions CI; git history to commit `97b6949` (27 Jul 2026).
- **Documents:** `CLAUDE.md` (7 non-negotiable principles), `README.md`, `HOW_TO_RUN.md`, `VIVA_PREP.md`, `FYP_REPORT_DRAFT.md`, `AUDIT_REPORT.md`, `EFFICIENCY_REVIEW.md`, `DASHBOARD_UX_REVIEW.md`, `FUTURE.md`, `FYP_Scope_Document_v2_0_1.docx`.
- **Known weaknesses recorded in the old project:** K_iz and K_exc are "representative" unattributed fits and are **ratio-coupled** (never refit one alone - see `error_fixing_attempts/`); the old engine's pressure range was 1-20 mTorr; gas flow and gas temperature were not physics inputs.

---

## 2b. State of this laptop (checked 2026-10-24/25)

- Python 3.14.7 and git 2.55 installed (user scope, via winget). Fresh `.venv` with the pinned `requirements.txt` plus the Reactor Control Room extras.
- Full old test suite: **374 passed, 1 skipped** (the skip is the optional PyTorch test module; 374 + 9 torch tests = 383).
- Old environment kept aside as `.venv_old` (about 1.6 GB, safe to delete).
- Git status is clean apart from untracked documents and the new questionnaire files.

---

## 3. The new direction in one paragraph

[SUP] The project changes from a semiconductor-process twin into **three mandatory stages**, with **Stage 1 the most important**. There are **two plasmas** and **two diagnostic techniques**: a low-pressure argon plasma generated in a chamber, and an underwater high-pressure oxygen plasma used to disinfect waste. Optical emission spectroscopy (OES) is used on **both**; the Langmuir probe is used on the **low-pressure argon plasma only**. The semiconductor-processing framing is removed. Both simulation and measured data are intended, with real data used for validation.

```
Plasma 1: low-pressure Ar (+N2, +O2) CCP in a chamber ----+--> OES (forward model + analysis of measured spectra)
                                                           +--> Langmuir probe (simulated I-V + analysis)
Plasma 2: underwater atmospheric-pressure O2 bubble discharge ---> OES (forward model + analysis)
                                                                 ---> disinfection model (E. coli)
Cross-check: OES-derived values compared with probe-derived values and the model.
```

Stage labels used in the questionnaires: **Stage 1** = low-pressure argon chamber (OES + Langmuir probe); **Stage 2** = underwater oxygen plasma; **Stage 3** = Langmuir probe (which, per [SUP] A1/D2, applies to the Stage 1 plasma only).

---

## 4. Supervisor answers - Round 1 (the first questionnaire, "SOLVED")

Where a ticked option and a typed note disagreed, the **note** is taken as the answer (the student confirmed the notes are authoritative).

### A. Overall scope
- **A1 (relationship of stages) [SUP]:** "two plasma are there: low pressure argon plasma which occur on chamber and other is underwater high pressure plasma, and OES and Langmuir are diagnostic techniques to measure plasma. OES is used in high pressure; for low pressure Langmuir probe and OES both are used." And: Langmuir probe happens only in argon; OES occurs on the underwater plasma and also on the low-pressure plasma.
- **A2:** the project should demonstrate a physically consistent simulation and agreement with published or experimental data.
- **A3:** simulation **plus** import of measured data (OES spectra, probe I-V curves) for comparison. **A3b:** "OES technique will measure real data".
- **A4:** remove the semiconductor-processing framing **entirely**.
- **A5:** benchmark against "available literature according to proposed experiment".
- **A6:** gases that may be added later: **nitrogen, oxygen**.
- **A7:** "stable plasma generation in chamber" (taken as the priority; see Section 5 for the later statement that all stages are mandatory).

### B. Stage 1 - low-pressure argon plasma
- **B1 operating envelope [SUP]:** RF power **10 to 100 W**; pressure **0.1 to 0.5 mbar** for low pressure (the underwater entry was cut off in the PDF; the underwater pressure is given as 1 atm in C2); RF frequency **13.56 MHz** for low pressure and **5 to 10 kHz** for the underwater plasma; discharge type **CCP**; chamber **40 x 40 cm**; other fixed parameters: **gas flow and gas concentration**.
- **B2 flow range:** **100 to 500 sccm** (continuous, "wider range" option).
- **B3 role of flow:** "gas is used for generation of reactive species or tuning of plasma parameter".
- **B4 OES mode:** **both** - synthesise spectra from the model and analyse measured spectra.
- **B5 spectral features:** Ar I lines (2p to 1s, about 690-850 nm) and the trace-N2 second positive system.
- **B6 gas temperature:** Doppler broadening of an argon line; note says both Doppler and rotational temperature "can be used depending upon type of gas".
- **B7 Boltzmann display:** Boltzmann plot (ln(I.lambda/gA) versus upper-level energy) **and** population distribution of excited levels, **and excitation temperature**.
- **B8 level populations:** **collisional-radiative (CR) model**.
- **B9 kinetic processes:** ground-state ionization and excitation; Penning / metastable-metastable ionization.
- **B10 electron energy distribution:** **Druyvesteyn for low pressure, Maxwellian for underwater** (the ticked "solve the Boltzmann equation" was overridden by the note).
- **B11 electron density in OES stage:** "Stark broadening of any gas we are using argon so argon" (later changed in Round 3 - see Section 5).
- **B12 outputs:** electron temperature and density; gas temperature; excitation temperature.
- **B13 instrument emulation:** left blank.
- **B14 rate-coefficient source:** "from any published data".

### C. Stage 2 - underwater oxygen plasma
- **C1:** plasma generated **inside gas bubbles in the water**.
- **C2:** supply **pulsed DC**; voltage **10 kV**; frequency **5 to 10 kHz**; pulse width "in micrometer" (see Round 3); electrode geometry **pin-to-pin**, gap "1 to" (cut off); pressure **1 atm**.
- **C3:** O2 flow **100 to 300**.
- **C4:** waste = **municipal waste**; other properties blank.
- **C5 organisms:** E. coli, S. aureus, bacterial spores.
- **C6 model:** **gas-phase global model plus empirical transfer of species into the liquid**.
- **C7 species:** O3, OH, H2O2, HO2/O2-, UV/photon effects.
- **C8 disinfection kinetics:** **Hom model**.
- **C9 outputs:** reactive-species concentrations versus time; pH, ORP and conductivity change; log reduction versus time; D-value / inactivation rate constant; energy yield; water temperature rise.
- **C10:** OES **is** applied to the underwater plasma, with the same diagnostic framework as Stage 1.
- **C11:** benchmark against "any published data".

### D. Stage 3 - Langmuir probe
- **D1:** **simulate** an I-V characteristic from the digital twin and analyse it to recover Te and ne (consistency check).
- **D2:** probe the **Stage 1 low-pressure argon plasma** only.
- **D3 probe type/geometry:** left blank.
- **D4 analysis theory:** **OML (orbital motion limited)** theory (the note repeats "OML theory").
- **D5:** model **RF sheath-oscillation distortion** of the I-V curve.
- **D7 outputs:** Te, ne, plasma potential Vp, floating potential Vf, EEDF/EEPF, Debye length.
- **D8:** **compare** OES-derived and probe-derived Te/ne side by side with the model.

### E. Fidelity, validation, AI
- **E1:** the 0D model alone is not enough: "needs spatial resolution (1D) for some quantities" (which quantities was not stated).
- **E2 agreement tolerance:** blank. **E3 role of AI:** blank. **E4/E5:** blank.

---

## 5. Resolutions after Round 1

### Student's instructions [STU]
- **Q10 (mandatory stages):** **all stages are mandatory; Stage 1 is the most important.**
- **Q1-Q8 (Round 2 open items):** "if there are figures on the internet related to the COMSATS Islamabad plasma physics lab, use them; otherwise use the default."

### Round 3 - supervisor answers [SUP] (questionnaire PDF "Round 3 done")
Respondent name was left blank in the PDF; the deadline question was not answered.

| # | Answer |
|---|---|
| Q1 trace gas | "5 percent nitrogen will go inside chamber which is 5 percent of argon gas we have already sent, and O2 will also go inside chamber and O2 will also be 5 percent of argon already sent." The yes/no tick was blank. |
| Q2 ne method | Low-pressure chamber: **the Langmuir probe value used as an input**. Underwater: **Stark broadening of H-alpha**. |
| Q3 underwater pulse | Unit: microseconds; pulse width "**100 micron**"; energy/power "**100 W**"; gap "**1 mm, 2 mm, 3 mm**". |
| Q4 survival data | Measured data: **planned / not yet measured**. Organisms: "any micro E. coli in water", "**1 to 2 lac CFU**" (lac = 100,000), "**1 min** treatment time"; "voltage optimum will be used", **O2 flow 100 sccm**, treatment time 1 min. If no data: "any available" published data. |
| Q5 gas temperature | Proposed default accepted (N2 rotational temperature from the (1,0) band at 315.8 nm with NH-overlap check; Doppler only if a high-resolution instrument is available) **and** he states a **high-resolution spectrometer is available** (Fabry-Perot or echelle, better than 0.01 nm). |
| Q6 AI layer | Default accepted: **optional, decide later**. |
| Q7 tolerance / 1D | Default accepted: **agreement within +/- 30 %; 1D only for Stage 1 spatial profiles; 0D elsewhere.** |
| Q8 measured data | **No OES spectra yet; probe curves planned.** Formats: Langmuir probe **.csv**; OES **text file**. Will send one sample of each type. **May the student use and cite the data in the report? No.** Validation set: "**all**" (all measured data held out for validation only). |
| Q9 deadline | **Not answered.** |

---

## 6. Resolved parameter table (supervisor first, literature only for blanks)

| Item | Value | Source |
|---|---|---|
| Plasma 1 gas | Argon + N2 (5 % of Ar flow) + O2 (5 % of Ar flow); mixing scheme to be confirmed | [SUP] |
| Plasma 1 flow | Ar 100-500 sccm; so N2 and O2 5-25 sccm each if "5 %" means 5 % of the Ar flow | [SUP]/[MINE] |
| Plasma 1 power | 10-100 W | [SUP] |
| Plasma 1 pressure | 0.1-0.5 mbar = 10-50 Pa = **75-375 mTorr** | [SUP]; conversion [MINE] |
| Plasma 1 drive | 13.56 MHz CCP | [SUP] |
| Plasma 1 chamber | 40 x 40 cm (the lab's published chamber is a cylinder 39 cm inner diameter x 42 cm high, 14 cm electrodes, 4.5 cm gap - consistent with his figure) | [SUP]; lab detail [LIT] |
| Plasma 1 EEDF | Druyvesteyn | [SUP] |
| Plasma 1 ne | From the probe value used as input (open question: circularity) | [SUP] |
| Plasma 1 Tgas | Doppler (argon line) and/or N2 rotational temperature | [SUP] |
| Langmuir probe | Single cylindrical tungsten probe, radius 0.195 mm, 5 mm exposed, sweep -20 V to +50 V in 0.5 V steps, cleaned at 150 V bias; OML analysis; Druyvesteyn second derivative for EEDF; RF distortion modelled | probe type blank in [SUP] -> dimensions from [LIT] (COMSATS lab paper); OML/RF distortion [SUP] |
| Plasma 2 gas | O2 bubble gas, 100 sccm (supervisor gave 100-300 in C3 and 100 sccm in Round 3); water vapour present (OH, H2O2, H-alpha seen) | [SUP]; water vapour [LIT] |
| Plasma 2 drive | Pulsed DC, ~10 kV, 5-10 kHz, **100 W average**, gap 1-3 mm, 1 atm | [SUP] |
| Plasma 2 pulse | Pulse width 100 "micron/microseconds" (inconsistent with 5-10 kHz - see Section 8). At 100 W: **10-20 mJ per pulse** at 10-5 kHz, close to the published ~17 mJ per pulse for microsecond bubble discharges | [SUP]; comparison [LIT] |
| Plasma 2 EEDF | Maxwellian | [SUP] |
| Plasma 2 ne | Stark broadening of H-alpha | [SUP] |
| Waste | Municipal waste; typical medium-strength values (COD 430 mg/L, BOD 190 mg/L, suspended solids 220 mg/L, dissolved solids 500 mg/L, pH ~7.5, 20-25 C). No conductivity figure found; ~750 uS/cm is the student-side estimate from dissolved solids | blanks filled from [LIT]/[MINE] |
| Organisms | E. coli (also S. aureus, spores listed); 1e5-2e5 CFU (per mL assumed), 1 min treatment | [SUP] |
| Disinfection model | Hom model; parameters (k, n, m) must be fitted - none found in the literature | [SUP]; gap [LIT] |
| Spectrometer (OES) | High-resolution instrument available (better than 0.01 nm); the published COMSATS underwater work used an Avantes multichannel spectrometer, 0.06-1.3 nm | [SUP]; [LIT] |
| Agreement tolerance | +/- 30 % | [SUP] (accepted default) |
| 1D | Stage 1 spatial profiles only | [SUP] (accepted default) |
| AI layer | **Core module** (student decision, 29-Oct-2026). Supervisor had said "optional, decided later". | [STU] overrides [SUP] |
| Semiconductor framing | Removed | [SUP] |
| Mandatory stages | All; Stage 1 first | [STU] |
| Deadline | Unknown | not answered |

---

## 7. Literature found (supporting facts)

The only COMSATS-linked sources found. No lab web page and no raw datasets are public.

1. **Wali et al., "Preliminary Exploration on the Low-Pressure Ar-O2 Plasma Generated by Low-Frequency AC Power Supply"**, arXiv:2405.05739 (2024) - authors include Q. U. Din and N. U. Rehman of the **Plasma Research Laboratory, Department of Physics, COMSATS University Islamabad**. Stainless-steel cylinder 39 cm inner diameter, 42.0 cm high; electrodes 14 cm diameter, 4.5 cm apart; pressure 0.5-0.7 mbar; flow 25 sccm; AC 6 kHz, 100-900 W; single Langmuir probe (tungsten, radius 0.195 mm, 5 mm exposed, sweep -20 to +50 V, 0.5 V step, 150 V cleaning, Impedans software; Vp by second-derivative zero crossing; EEDF by Druyvesteyn method). ne peaks near 400 W (example 7e15 m^-3); Te falls with power and pressure; EEDF non-Maxwellian. Bacteria: X. campestris 1e6 CFU/mL, about 75 % reduction after 180 s at 400 W, 0.5 mbar, 4 % O2. Data "available on reasonable request" from the corresponding author (Niaz Wali, niaz@zju.edu.cn). https://arxiv.org/pdf/2405.05739
2. **Ahmed et al., "DNA Reduction of Waterborne E. coli by Underwater Capillary Discharge"**, Jordan Journal of Physics 15(2), 2022 (co-author in COMSATS Islamabad physics; COMSATS microbiology lab supplied the bacteria). Quartz capillary (2 mm inner diameter), tungsten electrodes, AC 758 kHz, 5 mm gap, 3-7 kV, O2 300-600 sccm, water flow 0.1 L/min, E. coli about 1e7 CFU, Avantes spectrometer 0.06-1.3 nm; OES lines OH 309 nm, O 777 and 844 nm, H-alpha 656 nm. The paper's Hbeta (444 nm) and ozone (883 nm) labels look wrong and must not be copied unchecked (Hbeta is 486 nm). https://jjp.yu.edu.jo/index.php/jjp/article/download/638/194/2621
3. **Other COMSATS-lab RF work referenced by (1)** (not opened): Anjum and Rehman, *AIP Advances* 10 (2020), pulse-modulated capacitively coupled Ar/O2 discharge; Anjum, Younus and Rehman, *Physica Scripta* 95 (2020), He-O2/Ar mixture, 13.56 MHz CCP; Rehman et al. (2016), triple Langmuir probe in a 13.56 MHz inductively coupled plasma. These are the closest matches to the supervisor's low-pressure RF set-up and are good candidates for validation points.
4. **Underwater pulse energy:** about 17 mJ per pulse for microsecond discharges in gas bubbles (Boyko and Makogon, 2019); a single oxygen/argon bubble with 3-15 kV, 1 us pulses (Gershman et al.). https://doaj.org/article/a813a9eda13b426cb8ac4fe30abaefc7
5. **Municipal wastewater strength** (Metcalf and Eddy 2003, via UGA extension): medium COD 430 mg/L (weak 250, strong 800), BOD 190 mg/L. https://fieldreport.caes.uga.edu/wp-content/uploads/2025/08/C-992_6.pdf
6. **Argon CR models:** Zhu and Pu's simple CR model covers the Paschen 1s and 2p levels from 1 to 1e5 Pa; an 18-level model (ground state, four 1s, ten 2p) with rate coefficients from Zhu et al. is used for capacitively coupled argon; the 2p populations deviate from a Boltzmann distribution, so a Boltzmann-plot temperature is far below the CR electron temperature. https://arxiv.org/pdf/2010.10714
7. **Gas temperature from N2 in Ar-rich plasma:** the N2 rotational temperature can read far too high (1308 K at 1.8 % N2 in Ar, 50 W, 587 mTorr), probably because argon metastables populate the emitting state; using the (1,0) band at 315.8 nm and checking for NH overlap helps. https://link.springer.com/article/10.1007/s11090-025-10586-9
8. **Stark broadening:** useful only at very high electron density (published argon Stark work is at about 1e22 m^-3); a CR line-ratio method agrees with Stark broadening over roughly 1e11-1e16 cm^-3. The probe data from the COMSATS lab (about 7e15 m^-3) are well below the Stark range.
9. **Plasma-water disinfection energy:** one-log E. coli reduction needs about 14 to over 366 J/L; ozone appears to be the dominant agent.
10. **Doppler broadening of argon** (Ar 750 nm at 300 K) is only about 1-2 pm wide, so it needs a very high-resolution instrument (which the supervisor says is available).

---

## 8. Open questions, inconsistencies and risks

These are the points that must be settled before or while building. **All except item 7 need the supervisor or student to confirm.**

1. **Gas mixing (Round 3 Q1).** Are N2 and O2 added in the **same run** (Ar + 5 % N2 + 5 % O2) or in **separate runs**? If together, the plasma becomes electronegative and the argon-only CR model and the OML probe analysis are no longer sufficient. Also: is "5 %" of the **argon flow** (so 5-25 sccm each) or of the total?
2. **Underwater pulse width (Round 3 Q3).** 100 microseconds at 5-10 kHz is a 50-100 % duty cycle - not really pulsed. He may mean 100 ns, 10 us, or a lower frequency. Average power 100 W corresponds to 10-20 mJ per pulse.
3. **"Probe value as input" for ne (Round 3 Q2).** With no measured data, the probe is itself simulated from the twin, so using it as an input is circular. [MINE] proposal: the twin computes ne from its power balance, the simulated probe recovers it, and a real probe value overrides it when data exists.
4. **Hom model fitting (Round 3 Q4).** A single 1-minute treatment cannot fit three Hom parameters. Fitting needs time-resolved survival data (published or measured). Agreed approach to confirm: fit to published time-resolved data and present Hom as a model.
5. **Pressure units and envelope.** 0.1-0.5 mbar = **75-375 mTorr**, up to **about 19 times above the old engine's 1-20 mTorr upper limit**. The old collisionless Child-Langmuir sheath and the h-factor forms were chosen for the low range and are likely to fail; the engine must be extended (collisional sheath and ion transport). Confirm mbar (not mTorr) was meant. The lab's published runs were 0.5-0.7 mbar, 100-900 W AC at 6 kHz, 25 sccm - different from his 13.56 MHz, 10-100 W, 100-500 sccm.
6. **Data permission (Round 3 Q8).** "May use and cite: No", and no data exists yet. Validation therefore has to rest on **published literature**, with any later supervisor data used privately and held out ("all"). Confirm this is the intended meaning.
7. **Stark broadening vs probe ne.** In Round 3 he chose "probe value as input" for low-pressure ne, which sidesteps the problem that Stark broadening is unusable at low density. Underwater Stark broadening of H-alpha is physically reasonable because water vapour supplies hydrogen.
8. **Still blank:** deadline; E3 role of AI beyond "optional"; which quantities need 1D; probe type; spectrometer details beyond "high resolution"; bubble-gas composition (O2 only vs O2 + water vapour - water vapour is physically needed for OH and H2O2); waste conductivity and other properties; electrode geometry details beyond "pin-to-pin, 1-3 mm".
9. **O2 flow range** was 100-300 in C3 and 100 sccm in Round 3 - presumably 100 sccm is the operating point used for the survival experiment.

---

## 9. What stays, what changes, what is new (code-level plan)

### Keep and reuse
- Repository tooling: pytest, conftest, GitHub Actions CI, Streamlit + Plotly + SQLite + MLflow stack, `.gitignore`, launcher `.bat` files, `requirements.txt` pinning approach.
- Principles that still apply: outputs come from solved physics (not hand-fitted curves); seeds recorded; pre-registered parameters before any tuning; semi-quantitative validation with stated tolerances; honest reporting of failures; K_iz and K_exc must only ever be re-sourced together.
- Reusable code: `physics_engine.py` core (gas density, Bohm velocity, edge-to-center factors, Debye length, solve_electron_temperature / solve_plasma_density skeleton), `physics_validation.py` structure (`BenchmarkResult`), `session_manager.py` (SQLite sessions - schema to be generalised), `sensitivity_analysis.py` (sweep machinery), dashboard shell and caching pattern, Reactor Control Room components.

### Change
- **Physics engine:** pressure envelope (75-375 mTorr) and collisional sheath/ion transport; real gas-flow (residence-time) term in the particle balance; **gas temperature as a computed output** with an energy balance; **Ar/N2/O2 gas mixture** chemistry; **Druyvesteyn** (and Maxwellian) EEDF with rate coefficients derived from cross-sections; metastable and Penning processes; remove or retire the "indices" that were semiconductor-specific (reactivity, uniformity, etch rate, process quality, defect probability).
- **Chamber config:** new ranges (10-100 W, 0.1-0.5 mbar, 100-500 sccm), gas fractions, 40 x 40 cm geometry; rewrite the presets; drop the defect-probability warning.
- **Validation:** new reference checks for the CR model, Boltzmann plot and probe analysis; keep the old Turner checks as a reduced-equation test.
- **Sensitivity analysis:** add flow and gas-fraction sweeps.
- **Dashboard and Reactor Control Room:** restructure into Stage 1 (chamber + OES + probe), Stage 2 (underwater), validation and comparison pages.

### Retire or freeze (do not delete)
- `suitability_analysis.py` and `recommendation_engine.py` (semiconductor and quality-index based).
- `classification.py`, `anomaly_detection.py`, `autoencoder_detector.py`, `uncertainty_quantification.py`, `trend_analysis.py`, `correlation_analysis.py`, `training.py`, `dataset_generation.py`: frozen until the AI-layer decision; they may be retargeted later (for example, inferring plasma parameters from an OES spectrum).

### New modules
1. **OES (Stage 1):** 18-level argon CR model (ground, four 1s, ten 2p); synthetic spectrum builder with instrument function and noise (Ar I lines, N2 second positive (1,0) band near 315.8 nm, O I 777/844 nm); Boltzmann plot and excitation temperature; level-population distribution; Doppler and N2 rotational gas temperature; analysis of measured spectra (text-file import).
2. **Langmuir probe (Stage 1):** simulated I-V from the twin's plasma state; OML analysis, electron-retardation fit, Druyvesteyn second-derivative EEDF, Vp and Vf, Debye length; RF sheath-oscillation distortion; noise; csv import; OES-versus-probe-versus-model comparison.
3. **Underwater plasma (Stage 2):** bubble gas-phase global model for O2 + H2O with pulsed drive (100 W average); species O, O3, OH, H2O2, HO2/O2-, UV; empirical transfer into the liquid; pH/ORP/conductivity/temperature outputs; Hom disinfection model with log reduction, D-value and energy yield; OES on this plasma (O I 777/844, OH 309, H-alpha with Stark ne); Maxwellian EEDF.
4. **Data import layer** for .csv and text files; **validation** against published data.

---

## 10. Proposed build order (Stage 1 first)

1. Write the new scope document and update `CLAUDE.md` (revised principles: remove the semiconductor and classifier-significance principles; add the new stage structure, "supervisor answers authoritative", and the data-permission rule).
2. Stage 1 physics engine upgrade (units, pressure range, flow, gas temperature, gas mix) with tests.
3. OES forward model: CR model, spectrum, Boltzmann plot, gas temperature.
4. Langmuir probe simulation and analysis; OES-versus-probe comparison.
5. Stage 1 dashboard pages.
6. Stage 2 underwater model, Hom model and its OES.
7. Validation against published data; import tools for measured files; full test pass.
8. AI module (core): datasets and registry, spectrum inference, surrogate + SHAP, anomaly detection, twin-verified recommendations. See BUILD_STEPS.md Phases 9–13.
9. Report and viva preparation.

Rule carried over: build and test one module at a time; commit after each working sub-module with the sub-module named in the message.

---

## 11. Files created during this planning phase

This is a **new project with its own repository** (`plasma-digital-twin-v2`). The old `plasma-digital-twin` repository stays unchanged and is only a reference.

- `docs/supervisor/Supervisor_Questionnaire.html` - Round 1 form (answered; PDF returned as "SOLVED").
- `docs/supervisor/Supervisor_Questionnaire_Round2.html` - Round 2 form (Q2 and Q5 defaults updated to the COMSATS lab values; superseded by the student's own instructions).
- `docs/supervisor/Supervisor_Questionnaire_MeasuredData.html` - measured-data form (not yet answered by the supervisor; Round 3 Q8 covers part of it).
- `docs/supervisor/Supervisor_Questionnaire_Round3.html` - Round 3 form (answered; PDF returned "Round 3 done").
- `docs/srs/` - SRS v1.1 (Word + PDF), mockups, images and generator scripts.
- `docs/scope/` - Scope Document v3.1 of the new project.
- Questionnaire design: the PDF is generated from plain text built from the answers (so nothing can be clipped); a blank check runs before printing; important questions are marked.

---

## 12. Glossary

OES - optical emission spectroscopy. CCP - capacitively coupled plasma. CR model - collisional-radiative model of excited-level populations. EEDF/EEPF - electron energy distribution/probability function. OML - orbital motion limited probe theory. Druyvesteyn method - EEDF from the second derivative of the probe I-V curve. Boltzmann plot - ln(I.lambda/gA) versus upper-level energy; the slope gives an excitation temperature. Hom model - disinfection kinetics N/N0 = exp(-k C^n t^m). sccm - standard cubic centimetres per minute. 1 lac = 100,000.
