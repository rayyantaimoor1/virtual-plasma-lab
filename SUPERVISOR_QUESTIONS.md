# Questions for Dr. Majid Iqbal

Questions we need the supervisor to answer. Until they are answered, the project uses the default shown under **Until answered**, so work does not stop. When an answer arrives, write it under **Answer** with the date, then change the code or documents that depend on it.

The most urgent questions come first. Background for each one is in `docs/UNDERSTANDING.md`.

---

## Needed now (Phase 2: argon physics model)

### Q1. Published or laboratory values to check the argon model against
The model must match measured electron temperature (T_e) and electron density (n_e) within ±30 % at three or more operating points. The points must be argon at 13.56 MHz, 0.1–0.5 mbar.
- Which published papers do you trust for this? For example, Godyak et al. (1992) or work from the COMSATS Plasma Research Laboratory.
- Could the laboratory measure T_e and n_e with the Langmuir probe at three settings, for example 30 W, 50 W and 80 W at 0.3 mbar?

**Until answered:** we use open-access papers that report argon measurements at 13.56 MHz in this pressure range. Each value is recorded with its exact table or figure in `data/reference/constants/benchmarks.csv`.
**Answer:**

### Q2. Shape of the electrodes
Is the CCP symmetric (two electrodes of the same size, facing each other) or asymmetric (one powered electrode, with the grounded chamber wall as the other)? Are the electrodes 14 cm in diameter and 4.5 cm apart, as in the laboratory's published Ar–O₂ paper (Wali et al., 2024)?

**Until answered:** symmetric parallel plates, 14 cm in diameter, 4.5 cm apart, in a 40 cm × 40 cm chamber. The plasma is taken to fill the space between the plates.
**Answer:**

### Q3. Meaning of "10–100 W"
Is this the generator's forward power, or the power actually absorbed by the plasma? Some power is always lost in the matching network and cables, often 20–50 % in a CCP.

**Until answered:** the model treats it as power absorbed by the plasma. A coupling-efficiency setting can be added later if you give a typical value.
**Why it matters now:** the first comparison with published measurements gave an electron density 2–3 times too high (docs/validation/phase2_stage1_benchmarks.md). If only part of the generator power reaches the plasma, that explains some of the gap.
**Answer:**

### Q4. Pressure unit
Please confirm the unit is mbar (0.1–0.5 mbar = 75–375 mTorr) and not mTorr. The two are very different plasmas.

**Until answered:** mbar.
**Answer:**

---

## Needed for Phase 3 (gas flow, mixtures, gas temperature)

### Q5. Nitrogen and oxygen in the same run?
Are N₂ and O₂ added together in one run (argon + 5 % N₂ + 5 % O₂), or in separate runs? Is "5 %" measured against the argon flow, so 5–25 sccm each?

**Until answered:** the software offers all four choices (Ar, Ar+N₂, Ar+O₂, Ar+N₂+O₂). Each admixture is 5 % of the argon flow by default.
**Answer:**

### Q6. Measured gas temperature
Has the laboratory ever measured the gas temperature in this chamber, and with what method?

**Until answered:** the model calculates it from an energy balance and checks it against published argon CCP values.
**Answer:**

---

## Needed for Phases 4–5 (virtual OES and Langmuir probe)

### Q7. Spectrometer details
What are the spectrometer's model, wavelength range and resolution? You said it is better than 0.01 nm.

**Until answered:** 300–900 nm range, 0.005 nm resolution, 1 % noise.
**Answer:**

### Q8. Langmuir probe type
Is it a single cylindrical tungsten probe, 0.195 mm radius and 5 mm long, as in the published laboratory paper? Is it RF-compensated?

**Until answered:** yes to the size and shape. RF distortion is modelled, as you asked, through the RF amplitude left after compensation. It defaults to 0 V (fully compensated) until we know the laboratory probe's compensation, and can be set from 0 to 50 V.
**Answer:**

### Q9. Electron density in the low-pressure chamber
You said n_e should come from "the probe value used as an input". Without measured data, the probe is itself simulated from the model, so using it as an input would be circular.

**Until answered:** the model calculates n_e from its own power balance. The virtual probe tries to recover the same value, as a consistency check. A real probe value replaces it when measured data is imported.
**Found while building (3 Nov 2026):** when OES takes n_e from the probe, as you proposed, the OES T_e becomes very sensitive to it. A 10 % error in the probe's n_e moves the OES line-ratio T_e by about 30 %. Fitting T_e and n_e together from the spectrum avoids this. Which do you prefer?
**Answer:**

### Q10. Sample data files
You offered one sample OES text file and one probe .csv file. When can we have them? They show us the real file layout, even if we may not cite their values.

**Until answered:** we design the importers around common layouts (wavelength and intensity columns; voltage and current columns).
**Answer:**

---

## Needed for Phase 7 (underwater plasma)

### Q11. Pulse width
A 100 µs pulse at 5–10 kHz would leave the voltage on for 50–100 % of the time, which is barely pulsed. Did you mean 100 ns, 10 µs, or a lower frequency?

**Until answered:** 10 µs.
**Answer:**

### Q12. Gas inside the bubbles
Is it pure O₂, or O₂ with water vapour? Water vapour is needed to form OH, H₂O₂ and the H-alpha line used for n_e.

**Until answered:** O₂ with water vapour.
**Answer:**

### Q13. Disinfection data for the Hom model
The Hom model needs survival counts at several treatment times, not just one count after 1 minute. Can the laboratory measure survival at, say, 0, 0.5, 1, 2 and 5 minutes? Or which published data do you recommend?

**Until answered:** we fit the Hom model to published time-resolved *E. coli* data and say so clearly.
**Finding (4 November 2026):** no open-access paper matches our device (pin-to-pin, 5–10 kHz, O₂ bubbles) with survival at several times. So we use the published ozone kinetics of E. coli (Hunt & Mariñas 1997: first order, k = 130 L mg⁻¹ s⁻¹ at 20 °C, which is the Hom model with n = m = 1). The end-to-end ±30 % check waits for your survival data at, say, 0, 0.5, 1, 2 and 5 min.
**Answer:**

### Q19. How much of the power reaches the gas in the bubbles?
Our model sends only a share of the 100 W into the gas inside the bubbles; the rest heats the water. With all 100 W in the gas, every O₂ molecule would be split and no ozone would form. Do you have a measured ozone production (g/h or g/kWh), or the current through the water, for your set-up?

**Until answered:** the share is a visible input. Its default is 7.6 %, the largest share for which our chemistry stays valid (at most 10 % of the O₂ split per pulse). The results screen shows how much the answer depends on it.
**Answer:**

### Q14. Waste-water properties
Do you have measured conductivity, pH or COD for the municipal waste water?

**Until answered:** typical medium-strength values: conductivity 750 µS/cm, COD 430 mg/L, pH 7.5.
**Answer:**

---

## General

### Q15. Using your laboratory data in the report
You answered "No" to using and citing measured data in the report. Does that mean we may compare against it privately but not publish the numbers, or not use it at all?

**Until answered:** private comparison only. The report's validation rests on published literature.
**Answer:**

### Q16. Which quantities need 1D resolution
You said some quantities need a 1D profile. We plan an axial n_e profile between the electrodes for Stage 1. Is anything else needed?

**Until answered:** only the axial n_e profile.
**Answer:**

### Q17. Final submission deadline
What is the final submission deadline, and are there intermediate evaluations?

**Until answered:** unknown.
**Answer:**

### Q18. For information: the AI module is a core module
You marked the AI part as "optional, decide later". The team has decided to make it a core module alongside the digital twin, because the department values it. It learns only from data the twin generates. Please tell us if you disagree.

**Answer:**
