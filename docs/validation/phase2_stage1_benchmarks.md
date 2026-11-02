# Phase 2 benchmark comparison: argon global model vs Saikia et al. (2018)

**Run on:** 2 November 2026, model commit `0b15c93`, first comparison ever run.
**Rules:** fixed in `BUILD_STEPS.md` (Phase 2, "Benchmark comparison rules") and committed with the model before this run (ACC-4).
**Measurements:** Saikia et al., *AIP Advances* 8, 045113 (2018), Table II, RF-compensated Langmuir probe, argon, 13.56 MHz, 50 W (`data/reference/constants/benchmarks.csv`, commit `e28c89e`).
**Tolerance:** ±30 % (`envelope.toml`).

## Result: the exit-gate check FAILS

Pre-registered settings: Druyvesteyn EEDF, edge length 2·s_m, gas at 300 K, 50 W taken as absorbed power, symmetric electrodes of 4.5 cm radius, 7.5 cm gap.

| Point | Pressure | Quantity | Measured | Model | Difference | Within ±30 %? |
|---|---|---|---|---|---|---|
| 100 mTorr | 0.133 mbar | n_e (m⁻³) | 1.39 × 10¹⁶ | 3.63 × 10¹⁶ | +161 % | No |
| 100 mTorr | 0.133 mbar | T_e (eV) | 1.37 | 3.25 | +137 % | No |
| 200 mTorr | 0.267 mbar | n_e (m⁻³) | 1.62 × 10¹⁶ | 4.90 × 10¹⁶ | +202 % | No |
| 200 mTorr | 0.267 mbar | T_e (eV) | 1.34 | 3.01 | +125 % | No |
| 300 mTorr | 0.400 mbar | n_e (m⁻³) | 1.86 × 10¹⁶ | 5.90 × 10¹⁶ | +217 % | No |
| 300 mTorr | 0.400 mbar | T_e (eV) | 1.33 | 2.88 | +117 % | No |

What does agree: the trends. As pressure rises, the model's n_e rises (as measured), and its T_e changes only slightly (measured: nearly constant).

## For information only (cannot be used to pass)

| Settings | T_e difference at 100 / 200 / 300 mTorr | n_e difference at 100 / 200 / 300 mTorr |
|---|---|---|
| Maxwellian, edge 2·s_m | +32 / +20 / +13 % | +376 / +513 / +595 % |
| Druyvesteyn, edge = bulk | +132 / +118 / +110 % | +293 / +411 / +480 % |
| Maxwellian, edge = bulk | +26 / +13 / +6 % | +728 / +1178 / +1510 % |

No setting matches both T_e and n_e. A Maxwellian brings T_e close, but then n_e is even further off.

## What the result tells us

1. **The measured T_e is too low for single-step ionization.** In this geometry, even a Maxwellian plasma needs T_e ≈ 1.5–1.8 eV to replace the ions it loses by ionizing ground-state atoms. A measured 1.0–1.4 eV means the electrons get help: most likely two-step ionization through argon metastable atoms (Ar 1s₅, 1s₃, about 11.5 eV). These need far less energy per step, and they matter at n_e around 10¹⁶ m⁻³. The plan puts metastables in Phase 3, so the Phase 2 model leaves out a process the measurement says is active.
2. **"50 W" is probably generator power.** Saikia et al. give it as RF power from the generator through a matching network. A CCP often absorbs only 30–70 % of that. Since n_e grows about as P^0.66 in the model, absorbing half the power would lower n_e by about 37 %. This does not change T_e. See SUPERVISOR_QUESTIONS.md Q3.
3. **Probe T_e and model T_e may not measure the same thing.** The model's T_e is two-thirds of the mean energy. A probe's T_e taken from the slope of the current is set mostly by the slow electrons. With a Druyvesteyn-like distribution, the two can differ.
4. **Geometry and γ-mode.** Their electrodes are asymmetric, and the model has no secondary electrons. Both affect n_e more than T_e.

## What happens next

The Phase 2 exit gate is not passed. Any change to the model must be justified by physics stated in advance, not by this result. The comparison is then re-run against these same points, and this file keeps every run, so the history is visible.
