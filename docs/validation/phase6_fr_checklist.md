# Phase 6 requirement check: FR1.1 to FR7.6 against the screens

Checked on 3 November 2026, each requirement against its SRS text and acceptance criterion, on the running app and with the headless screen tests (`tests/test_app_screens.py`).

**Status words**
- **Met:** the screen does what the requirement and its acceptance criterion say.
- **Met, with a note:** it does so, but with a recorded difference.
- **Phase 8 / later:** deferred to a later phase by plan (BUILD_STEPS.md).

**"Fixed in this check"** marks gaps found by this check and closed before the Phase 6 push.

## M1 Home (FR1.1 to FR1.6)

| FR | Status | Where / note |
|---|---|---|
| FR1.1 Stage navigation | Met. Fixed in this check | Entry points: Stage 1, Stage 2, Diagnostics & data, and the AI module (Stage 1 listed first). Diagnostics & data was missing; Stage 2 and AI say "Built in Phase 7" and "Phases 9-13". |
| FR1.2 Quick start | Met | One click runs the default experiment and opens Results; the other presets run from the expander. Every preset is checked against the envelope by a test. |
| FR1.3 Recent sessions | Met. Fixed in this check | At most three sessions, newest first, with ID, stage, configuration and time. The button is "View all sessions". The list showed five before. |
| FR1.4 Usage role | Met | Student / Researcher switch in the sidebar, no login. |
| FR1.5 Reference data status | Met. Fixed in this check | Every data set with loaded / MISSING / CHANGED. The AI-model row ("not built yet") was added. The disinfection data arrive in Phase 7. |
| FR1.6 Help | Met | User guide and glossary expanders. |

## M2 Chamber configuration (FR2.1 to FR2.13)

| FR | Status | Where / note |
|---|---|---|
| FR2.1 RF power | Met | Linked slider and number box. |
| FR2.2 Pressure | Met | Shown in mbar, with Pa and mTorr. |
| FR2.3 RF frequency | Met | 13.56 MHz, not editable. |
| FR2.4 Argon flow | Met | Linked slider and number box. |
| FR2.5 Gas mixture | Met. Fixed in this check | Four mixture modes. A gas not in the mixture now keeps its field, disabled and showing 0. The resulting admixture flows are shown in sccm. |
| FR2.6 Geometry | Met | Four fields, each checked: > 0, electrode < chamber, gap < height. |
| FR2.7 EEDF | Met | Druyvesteyn is the default. |
| FR2.8 Spatial | Met | 0D or 0D+1D. |
| FR2.9 Preset and reset | Met | Presets and saved configurations can be loaded; reset returns the defaults. |
| FR2.10 Input validation | Met. Fixed in this check | Messages per field state the allowed range, and Run is disabled while any input is invalid. **Added:** a model-regime note. Before the run it gives the ion mean free path against the gap, and an O₂ warning when O₂ is present. After the run, the Results screen checks λ_i < s_m (collisional sheath). |
| FR2.11 Run simulation | Met | Opens Results. |
| FR2.12 Parameter sweep | Met. Fixed in this check | The admixture fraction (N₂ or O₂, when in the mixture) is now sweepable. Start < end inside the envelope is enforced; at most 200 points. |
| FR2.13 Save configuration | Met | Named; empty and duplicate names are refused. |

## M3 Results (FR3.1 to FR3.10)

| FR | Status | Where / note |
|---|---|---|
| FR3.1 Key results | Met | T_e, volume-averaged n_e, T_gas, ion flux. |
| FR3.2 Species densities | Met, with a note | The global model lumps the metastables (1s5 + 1s3) as in Kemaneci et al. (2016), the Phase 3 rule. The separate 1s levels come from the CR model on the OES screens. The two do not yet agree (open, BUILDING_JOURNEY Phase 4). |
| FR3.3 EEDF plot | Met | — |
| FR3.4 1D profile | Met | Only when 0D+1D is chosen. |
| FR3.5 Power balance | Met | Loss shares. |
| FR3.6 Model validity | Met | Assumptions expander. |
| FR3.7 Sweep results | Met | n_e and T_e against the swept parameter, with its label. |
| FR3.8 Send to diagnostics | Met | Buttons to M4 and M6. The open session's ID is shown in the sidebar. |
| FR3.9 Save session | Met | IDs S-0001, … never reused. |
| FR3.10 Export CSV | Met. Fixed in this check | The header now records the session ID and software version, then the configuration and results. |

## M4 Virtual OES (FR4.1 to FR4.8)

| FR | Status | Where / note |
|---|---|---|
| FR4.1 Synthetic spectrum | Met | — |
| FR4.2 Species toggles | Met. Fixed in this check | The toggles now really hide a species: its noise-free part is subtracted, so the noise is unchanged. A test checks that the parts add up to the full spectrum. N₂ can be enabled only when N₂ is in the mixture. O I is shown disabled until the oxygen lines come in Phase 7. |
| FR4.3 Instrument settings | Met. Fixed in this check | Integration time added (recorded in the export). The model gives power per volume, so it only scales counts; the noise setting stands for the resulting signal-to-noise. |
| FR4.4 Recompute | Met | Only the instrument model is reapplied (cached plasma). |
| FR4.5 Identified lines | Met. Fixed in this check | Added: E_k, g_k A_ki, relative intensity, and whether the line is in the Boltzmann plot (following the line choice on M5). N₂ bands are listed as "no (molecular band)". |
| FR4.6 Overlay measured | Phase 8 | Needs data import (M10). |
| FR4.7 Export spectrum | Met. Fixed in this check | Two-column text. Its header now records the session ID, software version and every instrument setting. |
| FR4.8 Analyse spectrum | Met | — |

## M5 OES analysis (FR5.1 to FR5.10)

| FR | Status | Where / note |
|---|---|---|
| FR5.1 Spectrum source | Synthetic: met. Imported: Phase 8 | — |
| FR5.2 Boltzmann plot | Met | — |
| FR5.3 Excitation temperature | Met | T_exc with standard error and R²; E9 flag. |
| FR5.4 Level populations | Met. Fixed in this check | **Added:** n_k/g_k of every CR level against Boltzmann at T_e from the ground state, with a statement when they are not in equilibrium. At the default the 2p levels hold about 10⁻⁷ of the Boltzmann value. |
| FR5.5 T_e by line ratio | Met | — |
| FR5.6 Gas temperature | Met, with a note. Fixed in this check | **Added:** a method choice, N₂ rotational (only with N₂; NH check) or Doppler (only when E8 allows). **Note:** Doppler uses Ar I 750.4 nm, not 811.5 nm. The 811.5 nm line ends on the metastable 1s5, so self-absorption would widen it (BUILD_STEPS.md, Phase 4e). The SRS text should be updated to match. |
| FR5.7 n_e used | Met | Value and source shown. |
| FR5.8 Select lines | Met | Excluded lines are in the export and now also shown on M4. |
| FR5.9 Compare | Met | — |
| FR5.10 Export | Met | — |

## M6 Langmuir probe (FR6.1 to FR6.10)

| FR | Status | Where / note |
|---|---|---|
| FR6.1 Probe geometry | Met. Fixed in this check | Probe type (single cylindrical, the only one modelled) and tip material (tungsten) are now shown as fields. |
| FR6.2 Voltage sweep | Met | — |
| FR6.3 RF distortion | Met | — |
| FR6.4 Noise level | Met | Seeded. |
| FR6.5 Generate I-V | Met | — |
| FR6.6 Analysis results | Met. Fixed in this check | **Added:** n_e from the OML ion current (Chen Eq. 22), labelled "approximate (O₂)" when O₂ is present (LI-4). It is fitted linearly to the current, I_i = −b√(V_p − V), so noise is not squared. Agreement with the model: within 1 % without noise; 15-22 % at the default 1 % noise (inside ±30 %). The EEPF and saturation n_e are still shown. |
| FR6.7 OML validity | Met | r_p/λ_D with an E12 warning. |
| FR6.8 EEPF | Met. Fixed in this check | The smoothing window (Savitzky-Golay, 5 points = 5 × step, order 3) is now shown with the result and written in the export. |
| FR6.9 Import measured I-V | Phase 8 | Needs data import (M10). |
| FR6.10 Compare / export | Met | The export header now records the session ID and probe settings. |

## M7 Comparison (FR7.1 to FR7.6)

| FR | Status | Where / note |
|---|---|---|
| FR7.1 Side-by-side | Met | Model, OES and probe values, with the maximum deviation. The comparison rules fixed in Phase 5 are unchanged: the new OML n_e is not added to the comparison. |
| FR7.2 Dependent values | Met | OES n_e taken from the probe is marked and not counted. |
| FR7.3 Verdict | Met | — |
| FR7.4 Deviation chart | Met | ±30 % band. |
| FR7.5 T_exc | Met | Shown, excluded, explained. |
| FR7.6 Assumptions | Met | Model, OES and probe. |

## Summary

| Status | Count |
|---|---|
| Met (including "with a note") | 60 of 63 |
| Partly: FR5.1 (synthetic met, imported spectrum in Phase 8) | 1 |
| Phase 8: FR4.6, FR6.9 (need data import) | 2 |
| Gaps found and fixed in this check | 16 (FR1.1, 1.3, 1.5, 2.5, 2.10, 2.12, 3.10, 4.2, 4.3, 4.5, 4.7, 5.4, 5.6, 6.1, 6.6, 6.8) |

**Tests added:**
- **Unit tests:**
  - admixture flows;
  - regime notes;
  - collisional sheath and the CSV header;
  - species parts that add up to the spectrum;
  - Boltzmann departure;
  - OML n_e with and without noise.
- **Screen tests:** five new tests for M1, M2, M4, M5 and M6.
