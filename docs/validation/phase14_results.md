# Phase 14 results: every requirement measured

**Measured on** 9 November 2026, on the version 0.13.0 code (twin version 1.0), released after the Phase 14 label and documentation fixes as 0.14.0, by the methods fixed in `BUILD_STEPS.md` (Phase 14 rules, commit `ad6e3b1`) before any measurement. The raw numbers are in `phase14_measurements.json`. Every functional requirement is checked in `phase14_fr_checklist.md`.

**The machine:**
- Intel i7-1355U: 10 cores (2 performance, 8 efficiency), 12 threads, 1.7 GHz base clock, turbo above 2.0 GHz.
- 15.6 GB RAM, Windows 11 Pro, Python 3.14.7.
- **Against the SRS reference computer** ("4-core, 2.0 GHz or faster"): this laptop's base clock is lower, but it has more cores and a much higher turbo speed.

**How the measurement runs went (all recorded, as the rules require):**
1. **Run 1** stopped at PER-3 with a bug in the script (`voltages` is a method). Nothing had been written yet. The bug was fixed.
2. **Run 2** completed every performance part (PER-1 to PER-10). It then broke at REL-1: the screen tests of PER-6 replace Python's `__main__`, so the process pool could not find its worker. The script now runs each part in its own process.
3. **Run 3** ran REL-1, REL-3, REL-4 and SEC-1.
   - **SEC-1 came back empty in both runs:** the script's commands run in a sandbox that cannot see other processes' sockets.
   - **So SEC-1 was measured on the running app instead,** from Windows PowerShell.

## Summary

| Requirement | Target | Measured | Result |
|---|---|---|---|
| PER-1 Stage 1 run | 95 % of 0D runs ≤ 2 s; 0D+1D ≤ 5 s | 95th percentile 1.03 s (0D, 100 runs); 0.35 s (0D+1D, 20 runs) | **Met** |
| PER-2 spectrum | ≤ 3 s | 0.28 s at most (600,001 points, see note) | **Met** |
| PER-3 probe | ≤ 2 s for 2,001 points | 0.007 s at most | **Met** |
| PER-4 sweep | ≤ 120 s, progress at least every 2 s | Phase 14: 17.5 s, but a spinner, not progress (partly met). **Phase 15:** a progress bar; 8.3 s, longest gap between updates 0.055 s | **Met (Phase 15)** |
| PER-5 Stage 2 run | ≤ 10 s | 0.57 s at most (10 runs) | **Met** |
| PER-6 input feedback | ≤ 0.5 s | 0.082 s at most (20 screen reruns); the validator alone 3–5 ms | **Met** |
| PER-7 50 MB import | ≤ 15 s | 0.71 s at most | **Met** |
| PER-8 start-up | ≤ 15 s | 8.1 s (server 3.0 s + Home drawn 5.1 s) | **Met** |
| PER-9 AI inference | ≤ 1 s | 0.31 s at most (first call with model loading: 5.0 s) | **Met** |
| PER-10 recommendation | ≤ 60 s, with progress | 1.0 s at most, 4 progress messages each | **Met** |
| REL-1 convergence | 100 % of ≥ 500 configurations | 1,000 of 1,000 | **Met** |
| REL-2 events | 27 of 27 give a message | Phase 14: 25 of 27, E4 and E18 gave an error trace (not met). **Phase 15:** 27 of 27; E18 retries once | **Met (Phase 15)** |
| REL-3 crash safety | 0 sessions lost in 50 kills | 0 lost of 1,176 committed; 0 corrupt | **Met** |
| REL-4 reproducibility | < 10⁻⁹ | 0 (identical, 697 numbers × 10 runs) | **Met** |
| USE-1 quick start | ≤ 2 interactions | 1 click | **Met** |
| USE-2 student test | ≥ 80 % of ≥ 5 students | not yet measured (sheet: `use2_test_sheet.md`) | **Not yet measured** |
| USE-3 inputs and errors | 100 % | inputs 44 of 44 (after fixes; before: 7 of 44 with a range); messages: see below | **Met after fixes** |
| USE-4 axes and glossary | 100 % | 24 of 27 axes (the 3 others are category axes); glossary 15 of 15 symbols (before: 6) | **Met, with a note** |
| USE-5 colour and contrast | never colour alone; ≥ 4.5:1 | labels on every status; text 9–18:1. Phase 14: primary buttons 3.3:1 (partly met). **Phase 15:** 6.6:1 in both themes | **Met (Phase 15)** |
| SEC-1 loopback only | no outside access | listens on 127.0.0.1 only; refused on all 3 network addresses | **Met** |
| SEC-2 files as data | 100 % | existing tests pass | **Met** |
| SEC-3 non-citable data | 0 in exports | existing tests pass | **Met** |
| SEC-4 parameterised SQL | 100 % | 28 SQL calls; every user value a `?` parameter (4 join constant text, reviewed) | **Met** |
| SEC-5 offline | no outbound connection | none attempted (new test) | **Met** |
| ACC-1 published values | ±30 % at ≥ 3 Stage 1 points, ≥ 1 Stage 2 point | Stage 1: 0 of 3 (n_e +159 to +216 %); Stage 2: no published data | **Not met** |
| ACC-2 diagnostics recover the model | probe ±10 %, OES ±30 % | existing tests pass | **Met** |
| ACC-3 balances | shares 100 ± 0.5 %, residual < 10⁻⁸ | 1,000 of 1,000; worst residual 9.8 × 10⁻¹¹ | **Met** |
| ACC-4 fixed before comparing | 0 changes after results | 0 (tolerance unchanged since commit 1) | **Met** |
| AIQ-1 spectrum inference | p < 0.05 against ridge; coverage ≥ 85 % | p = 0.49 / 0.51; T_e coverage 84 % / 80 % | **Not met** |
| AIQ-2 anomaly detection | recall ≥ 90 % at ≤ 5 % false alarms; above baseline | 100 % at 3.1 %; p = 1.9 × 10⁻⁹ | **Met** |
| AIQ-3 surrogate | R² ≥ 0.98, median error ≤ 5 %, ≥ 100× | Stage 1 met; Stage 2 median error up to 33 % | **Partly met** |
| AIQ-4 recommendations | 100 % twin-verified; ≥ 90 % of goals | 100 %; 30 of 30 | **Met** |
| AIQ-5 data discipline | settings fixed; runs logged; 0 trained on measured data | all 9 models on twin data, after the lock, logged | **Met** |
| AIQ-6 no stale model | 0 results from another twin version | all 9 models current; out-of-date models refused (test) | **Met** |
| MNT-1 tests and coverage | a test per module; ≥ 80 % | every module tested; 95.0 % overall (physics 98.0 %, AI 90.4 %) | **Met** |
| MNT-2 constants in data files | 100 % | Phase 14: rate fits and a dispersion formula in code (not met). **Phase 15:** moved to `stage1_constants.csv`; outputs bit-identical | **Met (Phase 15)** |
| MNT-3 hints and docstrings | 100 %, explaining the reason | present 342 of 342 (before: 214); a reason in 12 of a sample of 20 | **Partly met** |
| POR-1 install and start | one requirements file, one command, Windows and Ubuntu | Windows 11 here; Ubuntu in CI (install, tests, and now start-up) | **Met, with a note** |

**Count, after Phase 15 (10 November 2026):** 38 requirements:
- 33 met (including "met after fixes" and "met, with a note");
- 2 partly met (AIQ-3, MNT-3);
- 2 not met (ACC-1, AIQ-1);
- 1 not yet measured (USE-2).

**Correction (Phase 15, 10 November 2026):** the Phase 14 version of this line said "39 requirements: 27 met, 6 partly met, 5 not met, 1 not yet measured". That was a counting error: the table has 38 rows, and in Phase 14 they gave 29 met, 4 partly met (PER-4, USE-5, AIQ-3, MNT-3), 4 not met (REL-2, ACC-1, AIQ-1, MNT-2) and 1 not yet measured. The table rows themselves were right.

## Phase 15 re-measurements (10 November 2026)

The four gaps Phase 14 found were fixed by Phase 15 (rules in `BUILD_STEPS.md`, commit `7731b97`) and measured again by the same methods:

| Requirement | Phase 14 | Phase 15 |
|---|---|---|
| PER-4 sweep progress | a spinner for the whole sweep | a progress bar after every point: the longest gap between updates is 0.055 s over 200 points (limit 2 s); total 8.3 s (Phase 14: 17.5 s for the same solver work, probably the laptop's load at the time). In the browser the bar counted to 199 of 200, changing every 0.15–0.2 s |
| REL-2 events | 25 of 27 | 27 of 27. **E4:** every Stage 1 screen and M9 show "did not converge" with the reason, and no partial result. **E18:** the save is retried once after 0.5 s; then "Not saved (E18)", the reason, and the CSV download beside it. Both Phase 14 expected-failure tests now pass, plus two new ones (tried exactly twice; a save that fails once is stored) |
| USE-5 primary button | 3.3 : 1 | 6.57 : 1 in the light and the dark theme (`#B71C1C`). Body text, statuses and sidebar unchanged |
| MNT-2 constants | 14 rate-fit and formula numbers, plus 5 borderline factors, inside functions | 0. The fits (Kemaneci 2016 rows 7–22; Dong 2026 rows 16, 19, 21, 23–26; Peck & Reeder 1972) are in `data/reference/constants/stage1_constants.csv`, with a checksum. The textbook factors (1.73, 1.68, 1.52, 0.24, 0.92) are named, cited constants. Every model output is bit-identical (7,624 numbers compared, largest difference 0). The scan finds only the 26 allowed numbers |

**Found during the Phase 15 browser check:** setting `primaryColor` under `[theme]` silently turned off Streamlit's automatic dark theme. It is set under `[theme.light]` and `[theme.dark]` instead, and both themes were measured.

## Performance (PER) in detail

- **PER-1 (Stage 1 runs):** 100 configurations drawn across the envelope (all four mixtures, both EEDFs).
  - **0D:** median 0.72 s, 95th percentile 1.03 s, slowest 1.49 s.
  - **0D+1D:** 20 runs, slowest 0.64 s.
- **PER-2 (spectrum):** the SRS assumed 120,000 points for 300–900 nm at 0.005 nm. The spectrum is sampled five times finer than the line width, so it has 600,001 points, and it still takes at most 0.28 s.
- **PER-3 (probe):** the analysis stopped on none of the five plasmas.
- **PER-4 (sweep), partly met:** the sweep itself is fast: 200 points in 17.5 s, the slowest point 0.20 s, and all 200 solved. But M3 runs the whole sweep behind one spinner, so the user sees no progress, while the SRS asks for progress at least every 2 s (FR17.14). A per-point progress bar would meet it easily, but that is new code, which Phase 14 does not add. It is a follow-up.
- **PER-6 (input feedback):** the whole M2 or M8 screen redraws in 0.03–0.08 s after a changed value, including out-of-range values.
- **PER-7 (50 MB import):** OES text and probe CSV files of just under 50 MB, with 2.4 and 2.5 million rows, are each parsed and previewed in at most 0.71 s.
- **PER-8 (start-up):** the server answers its health check 3.0 s after `streamlit run`. A fresh Python process draws Home in 5.1 s, with no exceptions.
- **PER-9 (AI inference):** the model loads once, in 5.0 s for the first call; after that, calls take 0.27 s (median) and 0.31 s (slowest).

## Reliability (REL)

- **REL-1:** the grid was 4 mixtures × 5 powers × 5 pressures × 5 Ar flows × 2 EEDFs. All 1,000 configurations converge, which took 55 s on 6 processes. The 500-run test from Phase 2 still passes.
- **REL-3:** a child process saved sessions in a loop and was killed 50 times at random moments. It reported 1,176 committed sessions; every one was still there afterwards, and SQLite's integrity check said "ok" every time.
- **REL-4:** 10 configurations were each run twice and every numeric output compared (697 numbers per run). They are identical.

### REL-2: the 27 backend events

| Event | Checked by | Message shown |
|---|---|---|
| E1 Start-up | `test_home_runs_and_lists_reference_data`, `test_tracked_files_match_their_checksums` | yes (Home reference-data table) |
| E2 Stage 1 run | `test_quick_start_is_one_click_to_results` | yes |
| E3 Outside the envelope | `test_out_of_range_inputs_are_refused`, `test_chamber_screen_flags_an_out_of_range_value` | yes |
| **E4 Solver does not converge** | `test_a_solver_failure_shows_a_message_not_a_trace` (strict expected failure) | **no: an error trace** |
| E5 Pulse settings | `test_underwater_configuration_blocks_overlapping_pulses` | yes |
| E6 Reference data missing or changed | `test_changed_file_is_corrupt_and_refused`, `test_absent_file_is_missing_and_says_how_to_get_it` | yes |
| E7 Spectrum requested | `test_each_stage1_screen_runs[3_Virtual_OES]` | yes |
| E8 Doppler below resolution | `test_doppler_is_disabled_at_the_default_resolution` | yes |
| E9 Too few Boltzmann lines | `test_too_few_lines_or_too_narrow_a_span_is_flagged` | yes |
| E10 Probe curve requested | `test_probe_screen_reports_oml_density_type_and_smoothing` | yes |
| E11 Probe analysis fails | `test_failure_reports_the_step` | yes (now also says what to change) |
| E12 OML validity | `test_oml_check_reports_our_densities_as_outside_oml` | yes |
| E13 File uploaded | `test_measured_data_screen_lists_files_and_runs_validation` | yes |
| E14 File rejected | `test_bad_files_are_rejected_with_the_exact_reason`, `test_oversized_file_is_rejected` | yes |
| E15 Validation run | `test_results_are_recorded_with_date_and_version` | yes |
| E16 Tolerance exceeded | `test_thirty_one_percent_fails_and_twenty_nine_passes`, `test_benchmarks_list_source_values_and_results` | yes |
| E17 Sweep completed | `test_a_failed_point_is_kept_and_the_others_are_solved` | yes (no progress: PER-4) |
| **E18 Session save fails** | `test_a_failed_session_save_shows_a_message_and_keeps_the_results` (strict expected failure) | **no: an error trace, no retry** |
| E19 Export with non-citable data | `test_no_export_contains_a_non_citable_dataset` | yes |
| E20 Stage 2 run | `test_underwater_results_show_disinfection_and_save_a_stage2_session` | yes |
| E21 AI input outside the training range | `test_out_of_range_input_is_withheld` | yes |
| E22 AI model missing or out of date | `test_a_model_stamped_with_an_old_twin_version_is_out_of_date`, the "without a model" screen tests | yes |
| E23 AI training requested | `test_ai_training_screen_shows_datasets_and_gates_training` | yes |
| E24 Anomaly detected | `test_ai_anomaly_screen_checks_logs_reviews_and_exports` | yes |
| E25 Recommendation requested | `test_ai_recommend_screen_verifies_candidates_and_applies_one` | yes |
| E26 Goal unreachable | `test_an_impossible_goal_is_reported_as_unreachable_with_the_closest_option` | yes |
| E27 Surrogate and twin disagree | `test_twin_check_shows_the_twin_value_when_they_differ_by_more_than_5_percent` | yes |

**E4 and E18 in plain words:**
- **What is safe:** the model never returns half a result, and a failed save leaves the database untouched (REL-3).
- **What is wrong:** neither screen catches the error, so the user would see a Python trace instead of a sentence.
- **How likely:** E4 never happened in the 1,000-run grid, so a user is unlikely to meet it.
- **The fix:** two small error handlers (follow-up). The two strict expected-failure tests carry the finding until then.

## Usability (USE)

- **USE-2:** this needs real students, so it is not yet measured. The task card, observer rules and results table are in `use2_test_sheet.md`.
- **USE-3, inputs:** all 16 screens were opened in both roles, giving 44 distinct number inputs.
  - **Before:** 36 showed a unit and only 7 showed their allowed range.
  - **The fix (labels and help text only, allowed by the rules):**
    - every input's help tooltip now gives the envelope range, through `range_help()` in `app/common.py`;
    - geometry labels gained "(cm)";
    - the sweep's "From" and "To" gained the swept unit;
    - the power share and pH gained "(-)".
  - **After:** 44 of 44 show both.
- **USE-3, error messages:** every message from the validators, importers, sessions, measured-data store, probe analysis and screens was read.
  - **Already good:** the validators state the allowed range; the importers name the exact reason (and most say what to provide); the session and measured-data messages say what to do.
  - **Two groups were fixed (wording only):**
    - **Configuration errors** began with code names such as `electrode_gap_cm`. They now use the screen's names and end with "Change it to run."
    - **The five probe-analysis failures (E11)** said what failed but not what to change. Each now ends with the action, for example "widen the sweep" or "use a smaller voltage step".
  - **Still not ideal:** a few messages pass a technical reason through as it is (for example a stored file that no longer reads).
- **USE-4:** 27 axes in the default state of all screens.
  - **24 have a unit.** The other 3 are category axes, which list names, not quantities: the loss channels on M3, the diagnostics on M7 and the inputs on M15.
  - **The glossary:** it now covers every symbol on the axes and metric labels, 15 of 15. Before, it covered 6; P_abs, s_m, Γ, E_k, g_k, A_ki, n_k, r_p and T_eff were added.
  - **Limit:** charts that appear only after a button press were checked in the earlier phases' browser checks, not by this inventory.
- **USE-5:**
  - **Colour alone, met:** every status goes through `status()`, which adds "OK", "Note", "Warning" or "Error" (an automated test).
  - **Contrast**, measured in the browser with semi-transparent backgrounds blended in:

    | Element | Light theme | Dark theme |
    |---|---|---|
    | Body text, titles, captions, sidebar | 9.4–12.5 : 1 | 8.5–18.1 : 1 |
    | "OK" status (green) | 4.50 : 1 | 7.9 : 1 |
    | "Note" status (blue) | 6.7 : 1 | 4.9 : 1 |
    | "Error" status (red) | 4.57 : 1 | not shown in this check |
    | Primary button (white on Streamlit red) | **3.3 : 1** | **3.3 : 1** |

  - **The red primary buttons fail 4.5:1.** That is Streamlit's default theme colour. A darker `primaryColor` in `.streamlit/config.toml` would fix it (follow-up; it changes the look, not a label). The "Warning" status was not on screen during the check.

## Security (SEC)

- **SEC-1:** checked on the app as it runs (port 8501).
  - **Windows** lists one listening address, 127.0.0.1.
  - **Connections** through the laptop's three network addresses (private 192.168.x.x addresses) are refused, while 127.0.0.1 is accepted.
  - **Limit:** a scan from a second computer was not possible here.
- **SEC-4:** an automated check finds 28 SQL calls in `plasma_twin/`. Four build their SQL text by joining pieces, in `anomaly_log.py`, `db.py`, `measured.py` and `sessions.py`.
  - **Each was read:** they join only constant text written in the code (column names, a fixed SELECT, the schema version number).
  - **Every value a user can type is a `?` parameter.**
  - **A test** now fails if any other place builds SQL from text.
- **SEC-5:** a new test makes every connection that leaves the computer fail, and records it. Inside it runs:
  - a Stage 1 run, a spectrum, a probe curve and a Stage 2 run;
  - the AI inference, anomaly check, surrogate twin check and a recommendation.

  None tried to connect. Streamlit's usage statistics are off in its config (also tested).

## Accuracy (ACC)

No comparison was run or re-run in Phase 14.

- **ACC-1, Stage 1: not met.** The ±30 % benchmark against Saikia et al. (2018) failed in all three runs (Phase 2, `phase2_stage1_benchmarks.md`). In run 3:
  - **n_e:** +159 to +216 %;
  - **T_e (probe-style):** +54 to +69 %;
  - **the trends agree.**

  The likely causes are written there: two-step ionization, generator against absorbed power (Q3), and how a probe reads T_e. It is kept as a strict expected failure.
- **ACC-1, Stage 2: not met (open).** No published time-resolved survival data match this device. The Phase 7 exit gate was left open by team decision on 4 November, waiting for Q13.
- **ACC-2: met.** On a noise-free fine sweep, the probe analysis recovers the model's T_e and n_e within ±10 % (`test_noise_free_fine_sweep_recovers_model_te_and_ne`). The OES line-ratio fit gives back T_e and n_e within ±30 %, also with 1 % noise (`test_line_ratio.py`).
- **ACC-3: met** on the REL-1 grid:
  - all 1,000 runs have residuals below 10⁻⁸ (worst 9.8 × 10⁻¹¹);
  - heating and loss shares sum to 100 % within 3 × 10⁻¹³ %.
- **ACC-4: met.**
  - **The ±30 % tolerance** has been 0.30 since the first commit (`4cb95e3`, 1 November) and never changed.
  - **The benchmark values** (`benchmarks.csv`) were committed (`e28c89e`) before the first comparison (`af25866`) and have not changed since.
  - **The AI thresholds** (0.60, 0.75, 5 %) are unchanged since the first commit.

## AI quality (AIQ)

**AIQ-1, spectrum to plasma parameters (Phase 10):** 120 held-out runs on the random split, 34 on the region split.

| | RF, random | XGB, random | RF, region | XGB, region | Ridge, random | Physics fit, random |
|---|---|---|---|---|---|---|
| T_e MAE (eV) | 0.104 | 0.104 | 0.094 | 0.074 | 0.104 | 0.843 |
| n_e median error | 9.7 % | 9.1 % | 15.2 % | 11.4 % | 8.3 % | 32 % |
| T_e 90 % interval coverage | **84 %** | **80 %** | 91 % | 97 % | — | — |
| n_e coverage | 92 % | 89 % | 74 % | 85 % | — | — |
| p, T_e better than ridge | **0.49** | **0.51** | 0.77 | 0.16 | — | — |

- **Not met:** the trees are not significantly better than the ridge, and T_e coverage on the random split is below 85 %. Both are strict expected failures.
- **On other splits:** coverage averages 90 % over 30 other random splits (journey, Phase 10).
- **Against the physics fit:** the AI beats it clearly (p = 0.0005).

**AIQ-2, anomaly detection (Phase 12): met.**

| Split | Detector | Recall | False alarms | p against the range check |
|---|---|---|---|---|
| random | residual detector | **100 %** | **3.1 %** | 1.9 × 10⁻⁹ |
| random | range check | 74 % | 36 % | |
| region | residual detector | 100 % | 5.9 % | 0.12 |
| region | range check | 91 % | 47 % | |

**AIQ-3, surrogate (Phase 11):**

| | Stage 1 XGBoost | Stage 2 XGBoost |
|---|---|---|
| Worst R², random / region | 0.994 / 0.840 | 0.988 / 0.986 |
| Worst median error, random / region | 3.2 % / 5.5 % | **33 % / 36 %** (OH) |
| Speed-up in a 625-point map / one call | 20,020× / 157× | 5,941× / 39× |

- **Stage 1 meets everything.**
- **Stage 2** meets R² and speed, but not the median error: n_e 8 %, O₃ 12 %, H₂O₂ 18 %, OH 33 %, temperature rise 5.04 %. It is a strict expected failure.

**AIQ-4, recommendations (Phase 13): met.**
- **Twin-verified:** 100 % of candidates.
- **Benchmark:** the twin confirms 30 of 30 goals; 18 of 30 without the twin repair after the dated amendment (27 before it).

**AIQ-5: met.** All 9 registered models were trained on twin datasets (S1-…/S2-…), none on measured data.
- **The lock:** the dataset settings were locked on 4 November before the first model (4 November, 22:26).
- **Logging:** every training run is logged in MLflow.

**AIQ-6: met.** All 9 models are stamped with twin version 1.0 and are current. A model with another version is refused (`test_a_model_stamped_with_an_old_twin_version_is_out_of_date`).

## Maintainability (MNT)

- **MNT-1: met.** Line coverage over the whole suite (coverage.py 7.17.2):

  | Part | Lines covered |
  |---|---|
  | `plasma_twin/` (all) | 4,713 of 4,960 = **95.0 %** |
  | physics (`stage1`, `stage2`, `oes`, `probe`, `compare`, `reference`, `config`) | 2,447 of 2,497 = **98.0 %** |
  | `ai/` | 1,386 of 1,534 = **90.4 %** |
  | services / storage / data_io | 91.9 % / 97.9 % / 93.8 % |

  - **Lowest file:** `ai/training.py`, at 81 %.
  - **Every module is tested:** each is named in at least one test file (now a test).
  - **Limit:** code run inside worker processes is not counted, so the true coverage is a little higher.
- **MNT-2: not met.** The automated scan found 45 numbers with 3 or more significant figures inside physics functions. Each was read:
  - **Allowed (26):** grid sizes and iteration limits, rate-table bounds, spectral search windows, the 273.15 K offset and the 293.15 K / 298 K reference temperatures of the cited formulas, the J₀ Bessel zero, and the validity bands of the NIST Antoine data.
  - **Gaps (14 found by the scan, plus 5 borderline, and more like them):**
    - **Rate-coefficient fits written in code:** the argon excited-state rows in `argon_kinetics.py` and the O⁻/O₂(a) rows in `mixtures.py`. Each carries its table and row citation, but is not in a data file.
    - **The Peck & Reeder air-dispersion formula** in `n2_band.py`.
    - **Borderline (5):** the textbook coefficients 1.73, 1.68 and 1.52 in `global_model.py` and `mixtures.py`, which are part of the cited equations.

  Moving them to `data/reference/constants/` with their citations is a follow-up. It touches physics files, which Phase 14 does not change.
- **MNT-3: partly met.**
  - **Type hints and a docstring:** on 342 of 342 public functions and methods; before Phase 14, 214 had both (128 gaps).
  - **How the gaps were filled:** with docstrings and with type hints imported only for type checking, so nothing changed at run time.
  - **"Explains the physics or statistics reason":** judged on a random sample of 20 (seed 20261109). 12 explain the reason; 8 only say what the function does, mostly small helpers.

## Portability (POR-1)

- **One requirements file:** the app installs from `requirements.txt`, which is pinned and now includes `coverage==7.17.2`.
- **Windows 11:** the app starts with `streamlit run app/Home.py` on this laptop.
- **Ubuntu:** CI installs from the same file, runs the tests, and now (Phase 14) also starts the app with one command and checks that it answers.
- **Not tested:** CI uses Ubuntu "latest" (24.04), not 22.04, and Windows 10 was not available.

## Known failures and open items carried forward

- **Strict expected failures (6 after Phase 15; 8 in Phase 14):**
  - **AIQ-1:** T_e coverage (2 tests) and trees against the ridge (2 tests).
  - **AIQ-3:** the Stage 2 median error.
  - **ACC-1:** the Stage 1 benchmark.
  - **REL-2:** E4 and E18 (2 tests) were expected failures in Phase 14; they pass since Phase 15.
- **Open questions:** supervisor Q3 (generator or absorbed power), Q13 (published survival data), Q19 (the power share), the sample measured files, and the final deadline.
- **Open finding from Phase 10:** the physics line-ratio fit runs away to 6–9 eV for a quarter of the low-pressure spectra.
- **Follow-ups found by Phase 14:**
  1. **E4 and E18:** done in Phase 15.
  2. **Sweep progress (PER-4):** done in Phase 15.
  3. **Button contrast (USE-5):** done in Phase 15.
  4. **Constants (MNT-2):** done in Phase 15.
  5. **Docstrings:** give the 8 small helpers a reason, not just a description (still open).
  6. **USE-2:** run the student test (still open).

## What the Word report and the SRS/scope revision need

**The SRS needs a revision row for these changes since v1.1:**
- **Stage 2:** a "power share" input (Phase 7), and the pulse width default of 10 µs (Q11).
- **Phase 10 features:** line-area ratios of 20 Ar I lines.
- **The rule amendments:** Phase 12 (two residuals) and Phase 13 (the aim capped at the one-cell limit).
- **The new events behaviour:** E26 now shows the closest option.
- **Stage 1 recommendations:** they use RF power as the cost (no volume).
- **USE-3:** inputs state their range in a help tooltip.
- **The PER-2 point count:** 600,001, not 120,000.

**For the results chapters:** all the tables above, the FR checklist, the Phase 2 benchmark file, the per-phase "As built" sections in `BUILD_STEPS.md`, and the journey (`BUILDING_JOURNEY.md`).
