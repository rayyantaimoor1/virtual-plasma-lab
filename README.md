# AI-Assisted Plasma Process Experimentation & Digital Twin Analytics Platform

Final Year Project, BS Computer Science (2023–2027), COMSATS University Islamabad.

- Muhammad Rayyan Taimoor Khan (CIIT/FA23-BCS-072/ISB) — Digital Twin and physics core
- Sadeem Ur Rehman (CIIT/FA23-BCS-127/ISB) — Dashboard and analytics
- Supervisor: Dr. Majid Iqbal

A software-only virtual plasma laboratory in three stages, as defined by the supervisor:

1. **Stage 1:** low-pressure argon plasma. A 13.56 MHz CCP running at 10–100 W and 0.1–0.5 mbar, with Ar flow of 100–500 sccm and optional N₂/O₂. It is diagnosed by virtual optical emission spectroscopy (OES).
2. **Stage 2:** underwater pulsed-DC oxygen bubble plasma for disinfecting municipal waste water. It has its own OES and predicts *E. coli* inactivation with the Hom model.
3. **Stage 3:** Langmuir probe diagnostics of the Stage 1 plasma, using OML theory and the Druyvesteyn EEDF.

All three are cross-checked against each other and against published data within ±30 %.

The project has **two core modules**: Core Module 1, the **Digital Twin**, holds all of the physics above, and Core Module 2, the **AI Module**, learns from twin-generated data. The AI module infers plasma parameters from spectra, detects physics-relationship anomalies, provides a fast surrogate with SHAP explanations, and recommends settings that are verified by re-running the twin.

This is a **new project**. It is not a continuation of the earlier `plasma-digital-twin` repository, which is kept unchanged.

## Status

Phase 0 is complete: the project skeleton, operating-envelope configuration, SQLite schema and tests. No physics or AI has been built yet. See `BUILD_STEPS.md` for the plan.

## Running it

You need Python 3.12 or later. From the project folder on Windows:

```
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest
.venv\Scripts\python -m streamlit run app/Home.py
```

Run the last command from the project folder, because Streamlit reads its local-only settings from `.streamlit/config.toml` there.

## Repository layout

| Path | Contents |
|---|---|
| `app/` | Streamlit screens |
| `plasma_twin/` | All logic: configuration, storage, and later the physics and AI |
| `tests/` | pytest tests, one file per module |
| `data/`, `models/` | Reference data and trained AI models, added in later phases |
| `docs/scope/` | Scope Document v3.1 (Word + PDF) and its generator |
| `docs/srs/` | Software Requirements Specification v1.1, mockups, diagrams, generator |
| `docs/supervisor/` | Questionnaires sent to the supervisor |
| `docs/UNDERSTANDING.md` | Every supervisor answer, the literature used and the open questions |
| `docs/tools/` | Shared document-formatting helpers (python-docx) |

## Regenerating the documents

You need Python 3.12+ with `python-docx` and Microsoft Word on Windows.

```
python docs/scope/build/build_scope.py
powershell -File docs/scope/build/update_and_export.ps1
python docs/srs/build/build_srs.py
powershell -File docs/srs/build/update_and_export.ps1
```
