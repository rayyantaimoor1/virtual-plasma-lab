# Phase 14 requirement check: all 149 functional requirements

Checked on 9 November 2026 against the SRS text (`docs/srs/build/build_srs.py`), the screens and the tests. FR1 to FR7 were checked screen by screen in Phase 6 (`phase6_fr_checklist.md`); this file carries those results forward and adds FR8 to FR17.

**Status words:** **Met**; **Met, with a note** (met, with a recorded difference); **Partly met**; **Not met**.

**Summary after Phase 15 (10 November 2026):** 138 met, 10 met with a note, 1 partly met (FR9.3, waiting for published survival data), 0 not met (149 in all). In Phase 14 it was 135 met, 10 met with a note, 3 partly met, 1 not met; Phase 15 closed FR17.4, FR17.14 and FR17.15.

## M1 Home (FR1)

Evidence: Phase 6 check; tests/test_app_screens.py (Home tests).

| FR | Requirement | Status | Note |
|---|---|---|---|
| FR1.1 Stage navigation | The system shall display entry points to Stage 1 (Low-Pressure Plasma), Stage 2 (Underwater Plasma), Diagnostics & Data and the AI Module, each opening its first screen. | Met |  |
| FR1.2 Quick start | The system shall allow the user to choose a predefined example experiment and run it in a single action. | Met |  |
| FR1.3 Recent sessions | The system shall list the most recently saved sessions with session ID, stage, configuration summary and save time. | Met |  |
| FR1.4 Usage role | The system shall allow the user to switch between the Student and Researcher roles without logging in. | Met |  |
| FR1.5 Reference data status | The system shall display the load status of each reference data set (NIST atomic lines, LXCat cross-sections, N_2 band constants, disinfection reference data) and of the AI models. | Met |  |
| FR1.6 Help | The system shall provide a user guide and a glossary of the plasma terms and symbols used on the screens. | Met |  |

## M2 Chamber configuration (FR2)

Evidence: Phase 6 check; tests/test_app_screens.py, tests/test_stage1_service.py.

| FR | Requirement | Status | Note |
|---|---|---|---|
| FR2.1 RF power | The system shall accept the RF power through a linked slider and numeric field. | Met |  |
| FR2.2 Chamber pressure | The system shall accept the chamber pressure in mbar and display the equivalent value in Pa and mTorr. | Met |  |
| FR2.3 RF frequency | The system shall display the RF frequency as a fixed, non-editable value. | Met |  |
| FR2.4 Argon flow rate | The system shall accept the argon flow rate through a linked slider and numeric field. | Met |  |
| FR2.5 Gas mixture | The system shall allow the user to choose the mixture mode (Ar only, Ar + N_2, Ar + O_2, Ar + N_2 + O_2) and to enter each admixture as a percentage of the argon flow, showing the resulting flow in sccm. | Met |  |
| FR2.6 Chamber geometry | The system shall accept the chamber diameter and height, electrode diameter and electrode gap. | Met |  |
| FR2.7 EEDF | The system shall allow the user to select a Druyvesteyn or Maxwellian electron energy distribution. | Met |  |
| FR2.8 Spatial resolution | The system shall allow the user to choose the 0D global model or the 0D model with 1D axial profiles. | Met |  |
| FR2.9 Preset and reset | The system shall load a named preset and shall reset all fields to their defaults on request. | Met |  |
| FR2.10 Input validation | The system shall validate every parameter when it changes and display the envelope status and any model-regime note (for example, collisional sheath). | Met |  |
| FR2.11 Run simulation | The system shall run the Stage 1 simulation for the current configuration and open the results screen (M3). | Met |  |
| FR2.12 Parameter sweep | The system shall allow the user to define a sweep by choosing the swept parameter (RF power, pressure, argon flow or admixture fraction), the start and end values and the number of points. | Met |  |
| FR2.13 Save configuration | The system shall save the current configuration under a user-given name for later reuse. | Met |  |

## M3 Results (FR3)

Evidence: Phase 6 check; tests/test_app_screens.py (Results), tests/test_sweep.py.

| FR | Requirement | Status | Note |
|---|---|---|---|
| FR3.1 Key results | The system shall display T_e, volume-averaged n_e, T_gas and the ion flux to the electrode with units. | Met |  |
| FR3.2 Species densities | The system shall display the densities of ground-state Ar, Ar metastables (1s_5, 1s_3), Ar+ and the admixture species present in the selected mixture. | Met |  |
| FR3.3 EEDF plot | The system shall plot the electron energy distribution used in the run. | Met |  |
| FR3.4 1D profile | The system shall plot the axial n_e profile between the electrodes when 1D profiles were selected. | Met |  |
| FR3.5 Power and particle balance | The system shall display the share of absorbed power lost through each channel and the convergence status of the balances. | Met |  |
| FR3.6 Model validity | The system shall display the regime assumptions used in the run (sheath model, diffusion model). | Met |  |
| FR3.7 Sweep results | The system shall plot n_e and T_e against the swept parameter after a sweep. | Met |  |
| FR3.8 Send to diagnostics | The system shall pass the current plasma state to the virtual OES (M4) and the virtual Langmuir probe (M6). | Met |  |
| FR3.9 Save session | The system shall save the configuration and results as a session with a unique ID. | Met |  |
| FR3.10 Export CSV | The system shall export the results of the run as a CSV file. | Met |  |

## M4 Virtual OES (FR4)

Evidence: Phase 6 check; tests/test_spectrum.py, test_app_screens.py.

| FR | Requirement | Status | Note |
|---|---|---|---|
| FR4.1 Synthetic spectrum | The system shall compute and display the emission spectrum of the current plasma state from collisional-radiative level populations, with interactive zoom. | Met |  |
| FR4.2 Species toggles | The system shall allow the user to show or hide the Ar I, N_2 second positive system and O I contributions. | Met |  |
| FR4.3 Instrument settings | The system shall accept the instrument resolution (FWHM), wavelength range, noise level and integration time. | Met |  |
| FR4.4 Recompute | The system shall recompute the spectrum when the user changes the instrument settings and requests it. | Met |  |
| FR4.5 Identified lines | The system shall list the identified lines with wavelength, species, transition, upper-level energy, g_kA_ki, relative intensity and whether each line is used in the Boltzmann plot. | Met |  |
| FR4.6 Overlay measured | The system shall allow a Researcher to overlay an imported measured spectrum on the synthetic spectrum. | Met | Built in Phase 8 (it was 'Phase 8' in the Phase 6 check). Tested with synthetic measured files only; the supervisor's sample files have not arrived. |
| FR4.7 Export spectrum | The system shall export the spectrum as a two-column text file (wavelength, intensity). | Met |  |
| FR4.8 Analyse spectrum | The system shall open the OES analysis screen (M5) with the current spectrum. | Met |  |

## M5 OES analysis (FR5)

Evidence: Phase 6 check; tests/test_boltzmann.py, test_line_ratio.py, test_oes_gas_temp.py.

| FR | Requirement | Status | Note |
|---|---|---|---|
| FR5.1 Spectrum source | The system shall allow the user to analyse either the synthetic spectrum of the open session or (Researcher) an imported measurement. | Met | Synthetic since Phase 4; imported spectra since Phase 8 (test_researcher_overlays_and_imported_analysis). |
| FR5.2 Boltzmann plot | The system shall plot ln(Iλ/g_kA_ki) against upper-level energy for the selected Ar I lines and fit a straight line. | Met |  |
| FR5.3 Excitation temperature | The system shall report T_exc = −1/slope with its standard error and the R² of the fit. | Met |  |
| FR5.4 Level populations | The system shall display the CR-model populations of the excited levels against a Boltzmann distribution and state when the plasma is not in equilibrium. | Met |  |
| FR5.5 T~e~ by line ratio | The system shall estimate T_e by matching measured line-intensity ratios to CR-model predictions. | Met |  |
| FR5.6 Gas temperature | The system shall determine T_gas by the method selected: N_2 rotational temperature from the (1,0) band at 315.9 nm, or Doppler broadening of the Ar I 811.5 nm line. | Met |  |
| FR5.7 Electron density used | The system shall display the n_e used in the OES analysis and its source. | Met |  |
| FR5.8 Select lines | The system shall allow the user to include or exclude individual lines and shall refit immediately. | Met |  |
| FR5.9 Compare | The system shall open the comparison screen (M7) with the analysis results. | Met |  |
| FR5.10 Export results | The system shall export the analysis results and the fitted line list. | Met |  |

## M6 Langmuir probe (FR6)

Evidence: Phase 6 check; tests/test_probe_iv.py, test_probe_analysis.py.

| FR | Requirement | Status | Note |
|---|---|---|---|
| FR6.1 Probe geometry | The system shall accept the probe type, tip radius and exposed length; the tip material is shown as tungsten. | Met |  |
| FR6.2 Voltage sweep | The system shall accept the sweep start, end and step voltages. | Met |  |
| FR6.3 RF distortion | The system shall allow RF sheath-oscillation distortion of the I-V curve to be switched on or off. | Met |  |
| FR6.4 Noise level | The system shall accept a noise level for the synthetic current. | Met |  |
| FR6.5 Generate I-V curve | The system shall generate the synthetic I-V curve from the current plasma state and display it. | Met |  |
| FR6.6 Analysis results | The system shall determine V_f (zero current), V_p (zero crossing of d²I/dV²), T_e (slope of ln I_e in the retardation region), n_e (OML ion current) and λ_D. | Met |  |
| FR6.7 OML validity check | The system shall compute r_p/λ_D and report whether the OML assumption holds. | Met |  |
| FR6.8 EEPF | The system shall extract the EEPF from the second derivative of the I-V curve and plot it with a Maxwellian of the same mean energy. | Met |  |
| FR6.9 Import measured I-V | The system shall allow a Researcher to analyse an imported measured I-V curve with the same method. | Met | Built in Phase 8; tested with synthetic files only. |
| FR6.10 Compare / export | The system shall open the comparison screen (M7) and export the I-V curve and results. | Met |  |

## M7 Comparison (FR7)

Evidence: Phase 6 check; tests/test_compare.py.

| FR | Requirement | Status | Note |
|---|---|---|---|
| FR7.1 Side-by-side values | The system shall display T_e, n_e and T_gas from the model, OES and probe with the maximum deviation and a pass/fail flag. | Met |  |
| FR7.2 Dependent values | The system shall mark a value that one diagnostic takes from another (n_e in OES taken from the probe) and exclude it from the independent comparison. | Met |  |
| FR7.3 Verdict | The system shall show an overall verdict stating how many comparable quantities agree within tolerance. | Met |  |
| FR7.4 Deviation chart | The system shall plot the deviation of each diagnostic value with the ±30 % band. | Met |  |
| FR7.5 Excitation temperature | The system shall display T_exc but exclude it from the comparison with T_e and explain why. | Met |  |
| FR7.6 Method assumptions | The system shall list the assumptions of each method (model, OES, probe). | Met |  |

## M8 Underwater configuration (FR8)

Evidence: Phase 7; tests/test_pulse.py, test_app_screens.py (underwater configuration).

| FR | Requirement | Status | Note |
|---|---|---|---|
| FR8.1 Supply type | The system shall display the supply type as pulsed DC (fixed). | Met |  |
| FR8.2 Pulse voltage | The system shall accept the pulse voltage. | Met |  |
| FR8.3 Pulse repetition frequency | The system shall accept the pulse repetition frequency. | Met |  |
| FR8.4 Pulse width and duty cycle | The system shall accept the pulse width in µs and shall compute and display the duty cycle. | Met |  |
| FR8.5 Average power and energy per pulse | The system shall accept the average power and display the energy per pulse. | Met |  |
| FR8.6 Electrode gap | The system shall show the pin-to-pin electrode geometry (fixed) and allow a gap of 1, 2 or 3 mm. | Met |  |
| FR8.7 Pressure | The system shall display the pressure as 1 atm (fixed). | Met |  |
| FR8.8 Oxygen flow | The system shall accept the O_2 flow into the bubbles. | Met |  |
| FR8.9 Bubble gas | The system shall allow the bubble gas to be O_2 with water vapour or O_2 only. | Met |  |
| FR8.10 EEDF | The system shall display the Stage 2 EEDF as Maxwellian (fixed). | Met |  |
| FR8.11 Waste water properties | The system shall accept the water volume, conductivity, initial pH, temperature, COD and waste type. | Met |  |
| FR8.12 Target organism | The system shall allow the user to select the target organism (*E. coli*, *S. aureus*, bacterial spores) and enter the initial count and treatment time. | Met, with a note | All three organisms can be chosen. S. aureus and spores have no published kinetics, so a run with them is blocked with that reason (LI-6). |
| FR8.13 Run / reset / save | The system shall run the disinfection simulation, reset all fields to defaults, or save the configuration on request. | Met |  |

## M9 Underwater results (FR9)

Evidence: Phase 7; tests/test_bubble_model.py, test_liquid.py, test_hom.py, test_uw_oes.py, test_app_screens.py.

| FR | Requirement | Status | Note |
|---|---|---|---|
| FR9.1 Key results | The system shall display the log reduction at the treatment time, the D-value, the energy yield and the bubble plasma T_e and n_e. | Met |  |
| FR9.2 Reactive species | The system shall plot the concentrations of O_3, H_2O_2 and OH in the liquid against treatment time. | Met |  |
| FR9.3 Survival curve | The system shall plot log_10(N/N_0) from the Hom model against time, with published reference points. | Partly met | The Hom survival curve is plotted, but with no published reference points: no time-resolved data match this device (supervisor question Q13; Phase 7 exit gate left open by team decision). |
| FR9.4 Underwater OES | The system shall display the synthetic underwater spectrum (OH 309 nm, H-alpha 656.3 nm, O I 777 and 844 nm) and n_e from the H-alpha Stark width. | Met |  |
| FR9.5 Water chemistry | The system shall display pH, ORP, conductivity and temperature before and after treatment. | Met, with a note | pH, conductivity and temperature before and after; ORP is shown after treatment only (a Nernst estimate); before treatment it shows '-'. |
| FR9.6 Save / export | The system shall save the Stage 2 session and export its results as CSV. | Met |  |

## M10 Measured data and validation (FR10)

Evidence: Phase 8; tests/test_importers.py, test_validation.py, test_export.py, test_app_screens.py (measured data).

| FR | Requirement | Status | Note |
|---|---|---|---|
| FR10.1 Upload file | The system shall allow a Researcher to upload a measured OES spectrum (.txt) or Langmuir probe I-V curve (.csv) and report the number of rows read. | Met, with a note | Every FR10 screen works with synthetic test files; no real measured file has been imported yet (the supervisor's samples). |
| FR10.2 Metadata | The system shall require the diagnostic, plasma stage, operating conditions, gas mixture, measurement date and instrument for every file. | Met |  |
| FR10.3 Column mapping and units | The system shall allow the Researcher to map file columns to quantities and units and shall show a preview plot. | Met |  |
| FR10.4 Data use and citation | The system shall state that measured data are used for validation only and shall record a citation permission for each file. | Met |  |
| FR10.5 Save / cancel | The system shall save the file to the validation set or discard it on cancel. | Met |  |
| FR10.6 Literature benchmark | The system shall list each benchmark check with its reference source, computed value, reference value, deviation and result. | Met |  |
| FR10.7 Run validation | The system shall run all benchmark and measured-data comparisons on request. | Met |  |
| FR10.8 Validation report | The system shall generate a validation report of all checks. | Met |  |

## M11 Sessions (FR11)

Evidence: Phase 6; tests/test_sessions.py, test_export.py, test_app_screens.py (sessions).

| FR | Requirement | Status | Note |
|---|---|---|---|
| FR11.1 Session list | The system shall list saved sessions with ID, stage, configuration, key results, save time and note, filtered by stage and text search. | Met |  |
| FR11.2 Compare sessions | The system shall allow the user to select sessions and overlay their results in one chart. | Met |  |
| FR11.3 Open / replay | The system shall reopen a saved session, restoring its configuration and results. | Met |  |
| FR11.4 Delete | The system shall delete selected sessions after confirmation. | Met |  |
| FR11.5 Export | The system shall export the selected content (results tables, figures, raw spectra or I-V data) as a PDF report, CSV or PNG. | Met |  |

## M12 AI spectrum analysis (FR12)

Evidence: Phase 10; tests/test_ai_inference.py, test_app_screens.py (M12).

| FR | Requirement | Status | Note |
|---|---|---|---|
| FR12.1 Input spectrum | The system shall allow the user to choose the synthetic spectrum of the open session or (Researcher) an imported spectrum as input. | Met |  |
| FR12.2 Model selection | The system shall allow the user to choose an XGBoost model, a Random Forest model or the ridge-regression baseline. | Met, with a note | XGBoost or Random Forest can be chosen; the ridge baseline is shown beside them in the accuracy table, not offered as an estimator. |
| FR12.3 Infer parameters | The system shall estimate T_e, n_e and T_gas with 90 % conformal prediction intervals. | Met, with a note | 90 % intervals are shown; T_e coverage is 84 % / 80 % on the random split, below the 85 % of AIQ-1 (strict expected failure). |
| FR12.4 Physics comparison | The system shall show the physics-based value and the percentage difference next to each AI estimate. | Met |  |
| FR12.5 Training-range check | The system shall check that the input lies inside the training range of power, pressure, flow and mixture. | Met |  |
| FR12.6 Held-out performance | The system shall display the held-out error of the selected model, the baseline error, the interval coverage and the result of the significance test. | Met |  |

## M13 AI anomaly detection (FR13)

Evidence: Phase 12; tests/test_ai_anomaly.py, test_app_screens.py (M13).

| FR | Requirement | Status | Note |
|---|---|---|---|
| FR13.1 Check source | The system shall allow the user to check saved sessions or (Researcher) imported measured files. | Met, with a note | Measured files are checked with the single-instrument detectors; tested with synthetic files only. |
| FR13.2 Run anomaly check | The system shall compute residuals between the twin's predictions and the observed diagnostics and score them with an Isolation Forest. | Met |  |
| FR13.3 Checked runs | The system shall list each checked run with its anomaly score, severity, likely cause and the result of a simple range check. | Met |  |
| FR13.4 Score history | The system shall plot anomaly scores over the checked runs with the warning and critical thresholds. | Met |  |
| FR13.5 Explanation | The system shall show how much each residual contributed to a flagged run's score. | Met |  |
| FR13.6 Detector quality | The system shall display recall and false-alarm rate on held-out injected faults for the detector and for the range-check baseline. | Met |  |
| FR13.7 Review and export | The system shall allow the user to mark a flagged run as reviewed and to export the anomaly log. | Met |  |

## M14 AI recommendations (FR14)

Evidence: Phase 13; tests/test_ai_recommend.py, test_app_screens.py (M14).

| FR | Requirement | Status | Note |
|---|---|---|---|
| FR14.1 Goal | The system shall allow the user to choose the stage, an objective and a target value. | Met |  |
| FR14.2 Fixed settings | The system shall allow the user to keep chosen settings fixed during the search. | Met |  |
| FR14.3 Find settings | The system shall search the envelope on the surrogate and re-simulate the best three candidates with the digital twin (event E25). | Met |  |
| FR14.4 Ranked candidates | The system shall list each candidate's settings, surrogate prediction, twin-verified outcome, energy per litre and whether the goal is met. | Met, with a note | Stage 1 has no water volume, so its cost column is RF power (W), not energy per litre. |
| FR14.5 Energy chart | The system shall plot the twin outcomes of the candidates and the current run against energy per litre. | Met, with a note | Same: Stage 1 plots against RF power. |
| FR14.6 What-if | The system shall let the user change one setting of the current run and show the twin's re-simulated outputs. | Met |  |
| FR14.7 Apply or save | The system shall apply a chosen candidate to the configuration screen or save the recommendation. | Met |  |
| FR14.8 Unreachable goal | The system shall state when no setting inside the envelope reaches the goal and show the closest twin-verified option. | Met |  |

## M15 AI surrogate and SHAP (FR15)

Evidence: Phase 11; tests/test_ai_surrogate.py, test_app_screens.py (M15).

| FR | Requirement | Status | Note |
|---|---|---|---|
| FR15.1 Stage and output | The system shall allow the user to choose the stage and the output to explore. | Met |  |
| FR15.2 Fast map | The system shall draw a map of the chosen output over two inputs using the surrogate. | Met |  |
| FR15.3 Check with twin | The system shall re-run a selected point through the twin and show both values. | Met |  |
| FR15.4 Global explanation | The system shall show global SHAP importance of each input for the chosen output. | Met |  |
| FR15.5 Local explanation | The system shall show the SHAP contribution of each input for the current run. | Met |  |
| FR15.6 Surrogate accuracy | The system shall display R², median relative error and speed-up against the twin for each output. | Met, with a note | Shown for every output; the Stage 2 surrogate misses the 5 % median-error mark of AIQ-3 (strict expected failure). |

## M16 AI training and models (FR16)

Evidence: Phase 9; tests/test_ai_datasets.py, test_ai_registry.py, test_app_screens.py (M16).

| FR | Requirement | Status | Note |
|---|---|---|---|
| FR16.1 Training data | The system shall display the dataset ID, twin version, number of runs per stage and fault type, and the seed. | Met |  |
| FR16.2 Train a model | The system shall allow a Researcher to train a model by choosing the task, the algorithm and the evaluation split. | Met |  |
| FR16.3 Evaluation | The system shall evaluate every model on a random split and a region-based split and plot predicted against twin values. | Met |  |
| FR16.4 Model registry | The system shall list every model with its task, dataset, twin version, key held-out result, baseline result and status. | Met |  |
| FR16.5 Model card and runs | The system shall open a model's card and compare logged training runs. | Met |  |

## Backend events (E1-E27) (FR17)

Evidence: see the event table in phase14_results.md (REL-2).

| FR | Requirement | Status | Note |
|---|---|---|---|
| FR17.1 E1 | The system shall verify the presence and checksum of every reference data file and open or create the session database at start-up. | Met |  |
| FR17.2 E2 | The system shall compute the Stage 1 plasma state by solving the particle balance for T_e and then the power balance for n_e, reusing a cached result for an identical configuration. | Met, with a note | Runs are cached by the configuration's JSON. The cache lives for one app process, so a new model version is picked up on restart. |
| FR17.3 E3 | The system shall block a run while any input is outside its allowed range and shall state the allowed range. | Met |  |
| FR17.4 E4 | The system shall retry a non-converged solve once with a widened bracket and otherwise report failure without showing partial results. | Met (Phase 15) | Phase 14: partly met (the solver retries with a second method, but the screens showed an error trace). Phase 15: every Stage 1 screen and M9 show a 'did not converge' message with the reason and no partial result. |
| FR17.5 E5 | The system shall block a Stage 2 run whose duty cycle is 1 or more. | Met |  |
| FR17.6 E6 | The system shall disable features whose reference data are missing or corrupt and show this on the Home screen. | Met |  |
| FR17.7 E7 | The system shall synthesise spectra from CR-model populations and NIST line data with a seeded instrument noise model. | Met |  |
| FR17.8 E8 | The system shall disable Doppler gas-temperature analysis when the instrument FWHM exceeds the expected Doppler FWHM. | Met |  |
| FR17.9 E9 | The system shall not report T_exc unless at least 4 lines spanning at least 1.0 eV are used. | Met |  |
| FR17.10 E10, E11 | The system shall generate and automatically analyse probe curves and report the step at which an analysis fails. | Met |  |
| FR17.11 E12 | The system shall flag probe-derived n_e as approximate when r_p/λ_D > 1. | Met |  |
| FR17.12 E13, E14 | The system shall parse uploaded files and reject wrong-type, oversized or unparsable files with the exact reason. | Met |  |
| FR17.13 E15, E16 | The system shall evaluate every validation check against the ±30 % tolerance loaded from the versioned file and record failures without changing model parameters. | Met |  |
| FR17.14 E17 | The system shall show sweep progress and keep all solved points when some points fail. | Met (Phase 15) | Phase 14: partly met (a spinner, not progress). Phase 15: a progress bar after every point; longest gap 0.055 s over 200 points (PER-4). |
| FR17.15 E18 | The system shall keep results in memory and offer CSV export when a session cannot be saved. | Met (Phase 15) | Phase 14: not met (no retry, an error trace). Phase 15: one automatic retry after 0.5 s, then 'Not saved (E18)' with the reason; the results stay on screen with the CSV download beside it. |
| FR17.16 E19 | The system shall exclude non-citable measured data from every export and report the number excluded. | Met |  |
| FR17.17 E20 | The system shall compute the Stage 2 bubble plasma, liquid species, Hom survival, water chemistry and underwater spectrum in one run. | Met |  |
| FR17.18 E21, E22 | The system shall withhold AI estimates outside the training range and shall not use any AI model that is missing or trained on an older twin version. | Met |  |
| FR17.19 E23 | The system shall train each AI model together with its baseline on twin-generated data, evaluate both on random and region splits, and log the run with MLflow. | Met |  |
| FR17.20 E24 | The system shall flag runs whose anomaly score reaches the warning threshold and record the likely cause. | Met |  |
| FR17.21 E25, E26 | The system shall verify every recommendation candidate with the twin and report when a goal cannot be reached inside the envelope. | Met |  |
| FR17.22 E27 | The system shall prefer the twin value whenever the surrogate differs from it by more than 5 %. | Met |  |

