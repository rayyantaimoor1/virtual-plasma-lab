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

---

# Run 2: with excited atoms and two-step ionization (Phase 2d)

**Run on:** 2 November 2026, model commit `db2a982`. Same points, settings, geometry, tolerance and pass rule as run 1. The only change is the 2d excited-state kinetics, fixed in `BUILD_STEPS.md` before the run.
**Openly stated:** while the 2d code was being tested, the full test suite also ran the gate test once, so we knew the gate still failed before this record was written. The model was not changed after that; it was committed as tested.

## Result: the exit-gate check still FAILS

| Point | Pressure | Quantity | Measured | Model (run 2) | Difference (run 2) | Run 1 |
|---|---|---|---|---|---|---|
| 100 mTorr | 0.133 mbar | n_e (m⁻³) | 1.39 × 10¹⁶ | 3.60 × 10¹⁶ | +159 % | +161 % |
| 100 mTorr | 0.133 mbar | T_e (eV) | 1.37 | 3.24 | +136 % | +137 % |
| 200 mTorr | 0.267 mbar | n_e (m⁻³) | 1.62 × 10¹⁶ | 4.87 × 10¹⁶ | +201 % | +202 % |
| 200 mTorr | 0.267 mbar | T_e (eV) | 1.34 | 2.99 | +123 % | +125 % |
| 300 mTorr | 0.400 mbar | n_e (m⁻³) | 1.86 × 10¹⁶ | 5.89 × 10¹⁶ | +216 % | +217 % |
| 300 mTorr | 0.400 mbar | T_e (eV) | 1.33 | 2.86 | +115 % | +117 % |

Two-step ionization makes 4.7 %, 7.8 % and 10.5 % of the ions at the three points, and the metastable density is 1.2–1.6 × 10¹⁷ m⁻³. With the Maxwellian EEDF (information only), T_e is +32, +19 and +12 % off and n_e +372 to +589 %.

## What run 2 tells us

1. **Metastables are not what separates model and measurement.** In this model, at T_e near 3 eV, ionization from the ground state still dominates. Metastables are quickly turned into resonant atoms by electron collisions (row 9 of the reaction set), so they never build up enough to take over. Hypothesis 1 of run 1 is therefore ruled out as the main cause.
2. **The T_e gap is most likely a question of what "T_e" means.** With a Druyvesteyn EEDF, the model needs a mean energy equal to T_e ≈ 3 eV to make enough fast electrons. A probe reading T_e from the slope of its current near the floating potential sees mainly the slow electrons, and reports a lower number for the same distribution. Comparing like with like needs the probe-equivalent T_e of the model's EEDF. That is what the virtual Langmuir probe of Phase 5 computes.
3. **The n_e gap still points to absorbed versus generator power** (SUPERVISOR_QUESTIONS.md, Q3), and to the asymmetric electrodes and missing γ-mode heating.

---

# Run 3: comparing T_e the way the probe measured it

**Run on:** 2 November 2026, code commit `c09ba4e`; rule fixed in commit `78c2739` before any code was written.
**What changed:** only the T_e being compared. Saikia et al. derived T_e "from the linear part of the logarithmic electron current". So the model's T_e is converted to what that slope method would read from the model's own EEDF. A straight line is fitted to ln I_e between the plasma potential and the floating potential (`plasma_twin/probe/retardation.py`). The model itself, n_e and every other setting are unchanged from run 2.
**Openly stated:** for a fixed EEDF shape, the probe reading is a fixed fraction of the mean-energy T_e (0.713 for Druyvesteyn with the full window). This fraction was printed while testing the code, before the run, so the T_e outcome could be worked out in advance. Nothing was changed because of it. This time the full test suite was run without the benchmark file before the commit.

## Result: the exit-gate check still FAILS

| Point | Pressure | Quantity | Measured | Model (run 3) | Run 3 | Run 2 |
|---|---|---|---|---|---|---|
| 100 mTorr | 0.133 mbar | n_e (m⁻³) | 1.39 × 10¹⁶ | 3.60 × 10¹⁶ | +159 % | +159 % |
| 100 mTorr | 0.133 mbar | T_e, probe-style (eV) | 1.37 | 2.31 | +69 % | +136 % |
| 200 mTorr | 0.267 mbar | n_e (m⁻³) | 1.62 × 10¹⁶ | 4.87 × 10¹⁶ | +201 % | +201 % |
| 200 mTorr | 0.267 mbar | T_e, probe-style (eV) | 1.34 | 2.13 | +59 % | +123 % |
| 300 mTorr | 0.400 mbar | n_e (m⁻³) | 1.86 × 10¹⁶ | 5.89 × 10¹⁶ | +216 % | +216 % |
| 300 mTorr | 0.400 mbar | T_e, probe-style (eV) | 1.33 | 2.04 | +54 % | +115 % |

For information only (cannot be used to pass):
- **Only the half of the window near the plasma potential:** T_e +111, +99, +92 %.
- **Only the half near the floating potential:** +39, +32, +27 %.
- **Maxwellian EEDF:** probe-style T_e equals its mean-energy T_e, giving +32, +19, +12 %.

## What run 3 tells us

1. **The definition of T_e explains about half of the T_e gap.** Comparing like with like brings the difference from about +125 % down to about +60 %. This was a real mismatch between model and measurement, now fixed for every future comparison.
2. **The rest of the T_e gap depends on the EEDF shape and on where on the I-V curve the line is fitted.** The paper does not state its fit window. Fitted near the floating potential, the same model reads within about 30–40 %. We report this but do not use it, because the window was fixed beforehand as the full transition region. Both the window and the measured EEDF shape would settle it: they belong with the virtual probe (Phase 5) and the laboratory's own probe data (SUPERVISOR_QUESTIONS.md, Q1 and Q10).
3. **n_e is now the bigger problem, and T_e changes do not touch it.** At 50 W the model's density is 2.6–3.2 times the measured one. The leading explanation is that "50 W" is generator power and the plasma absorbs much less (Q3). The asymmetric electrodes and the missing γ-mode heating also act on n_e.
