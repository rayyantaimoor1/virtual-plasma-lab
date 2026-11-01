"""Home page (minimal Phase 0 version of mockup M1).

It proves the three layers connect: the screen runs, the envelope loads, and the database opens.
The full M1 screen is built in Phase 6.
"""
import sys
from pathlib import Path

# `streamlit run app/Home.py` puts app/ on the import path, not the project root, so the
# plasma_twin package would not be found without this line.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from plasma_twin.config.loader import iter_ranges, load_envelope  # noqa: E402
from plasma_twin.storage.db import SCHEMA_VERSION, init_db  # noqa: E402

st.set_page_config(page_title="Plasma Digital Twin")
st.title("Plasma Digital Twin")

envelope = load_envelope()
init_db()

st.success(f"Operating envelope {envelope['config_version']} loaded: {len(list(iter_ranges(envelope)))} ranges.")
st.success(f"Database ready: schema version {SCHEMA_VERSION}.")
st.caption("Phase 0 skeleton. The simulation screens are built in later phases.")
