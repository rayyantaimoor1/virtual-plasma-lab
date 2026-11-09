# USE-2 student test: configure a Stage 1 run and read T_gas

**What USE-2 asks:** at least 80 % of at least 5 student test users configure a stated Stage 1 run and read the gas temperature T_gas within 5 minutes, without help.

**Why this is a sheet and not a result:** it needs real students, so it cannot be measured by a script. Until it is run, USE-2 is recorded as "not yet measured" in `phase14_results.md`.

## Before each student

1. Start the app (`streamlit run app/Home.py`) and open it in the browser on the Home screen.
2. Use a fresh browser tab, so no earlier settings are kept.
3. Have a stopwatch ready. Do not show the student the app beforehand.
4. Choose students who have **not** used this app. Plasma background is fine; app experience is not.

## Task card (print this part and give it to the student)

> Using the Plasma Digital Twin, simulate this low-pressure argon plasma:
>
> - RF power **80 W**
> - Pressure **0.20 mbar**
> - Argon flow **250 sccm**
> - Gas mixture **Ar + N₂**, with N₂ at **3 %**
> - Everything else as it is
>
> Then find and write down the **gas temperature T_gas** (in kelvin) that the simulation gives.
>
> Gas temperature: ______________ K

## Rules for the observer

- Start the stopwatch when the student gets the card. Stop it when they write down a value.
- **No help:** do not answer questions about the app. Only say "please do what you think is right".
- **Success** means the value is within ±0.5 K of the reference value below, and it was written down within 5:00.
- Note where the student hesitated, or where they went wrong. These notes improve the app.

**Reference value:** run the configuration yourself once, before the first student, and write the T_gas the Results screen shows here: ______________ K

## Results

| # | Student (initials) | Time (m:ss) | T_gas written (K) | Within ±0.5 K? | Within 5:00? | Success? | Where they hesitated |
|---|---|---|---|---|---|---|---|
| 1 | | | | | | | |
| 2 | | | | | | | |
| 3 | | | | | | | |
| 4 | | | | | | | |
| 5 | | | | | | | |

**Result:** ____ of ____ succeeded = ____ %. USE-2 is met at 80 % or more, with at least 5 students.

Date: ______________  Observer: ______________

After the test, copy the result into `phase14_results.md` (USE-2 row), with the date.
