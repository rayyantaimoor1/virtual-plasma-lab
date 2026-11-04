"""Plasma Digital Twin: physics engine, virtual diagnostics and (later) the AI module.

__version__ is stored with every saved session (REL-4, FR11.3), so a session reopened after the
model has changed says so and offers a re-run. The minor number follows the build phase.
"""
__version__ = "0.9.0"
# The twin's physics version, separate from the software version above (Phase 9, AIQ-6, E22). Raise it only when
# the physics or the reference data change: every AI dataset and model is stamped with it, and a model stamped with
# another twin version is out of date and never used.
TWIN_VERSION = "1.0"
