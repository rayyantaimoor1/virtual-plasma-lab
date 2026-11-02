"""Tests for reference data (plasma_twin/reference/loaders.py).

Most tests use small fake files, so they run everywhere, including on GitHub. Tests marked
`real_data` check spot values in the downloaded files and are skipped where those are absent:
NIST and LXCat files are not in the public repository.
"""
import json
from pathlib import Path

import numpy as np
import pytest

from plasma_twin.reference.loaders import (
    EV_PER_CM1,
    MANIFEST_PATH,
    REFERENCE_DIR,
    DataStatus,
    ReferenceDataError,
    check_reference_data,
    load_atomic_lines,
    load_benchmarks,
    load_cross_sections,
    load_diatomic_constants,
    load_manifest,
    read_lxcat,
    read_nist_lines,
    sha256_of,
    verified_path,
)

# Invented numbers that only exercise the parser. They are not physical data.
FAKE_NIST = (
    "obs_wl_air(nm),ritz_wl_air(nm),Aki(s^-1),Acc,Ei(cm-1),Ek(cm-1),conf_i,term_i,conf_k,term_k,g_i,g_k,Type,\n"
    '"=""500.0""","=""500.01""","=""2.0e+07""",A,"=""1000.0""","=""21000.0?""","=""a""","=""b""","=""c""","=""d""",3,5,,\n'
    '"=""""","=""400.02""","=""1.0e+06""",B,"=""0.0""","=""25000.0""","=""a""","=""b""","=""c""","=""d""",1,3,,\n'
    '"=""450.0""","=""450.0""","=""""",,"=""0.0""","=""22000.0""","=""a""","=""b""","=""c""","=""d""",1,3,,\n'
)
# Same layout as a real Biagi download: labelled lines, tab-separated tables, and an attachment
# block with no threshold line.
FAKE_LXCAT = """LXCat, www.lxcat.net
Keyword in capitals indicating the type of the collision.
DATABASE:         FAKE
********************************* Fk *********************************

ELASTIC
Fk
 1.0e-5
SPECIES: e / Fk
PROCESS: E + Fk -> E + Fk, Elastic
PARAM.:  m/M = 0.00001, complete set
COMMENT: elastic momentum transfer.
UPDATED: 2024-02-16 13:00:39
COLUMNS: Energy (eV) | Cross section (m2)
-----------------------------
 0.0e+0\t1.0e-20
 1.0e+1\t2.0e-20
-----------------------------

EXCITATION
Fk -> Fk(1S5)
 1.15e+1
SPECIES: e / Fk
PROCESS: E + Fk -> E + Fk(1S5), Excitation
PARAM.:  E = 11.5 eV, complete set
COLUMNS: Energy (eV) | Cross section (m2)
-----------------------------
 1.15e+1\t0.0e+0
 2.0e+1\t3.0e-22
-----------------------------

ATTACHMENT
Fk -> Fk^-
SPECIES: e / Fk
PROCESS: E + Fk -> Fk-, Attachment
PARAM.:  E = 0 eV, complete set
COMMENT: 3-body attachment cross section is normalized to gas density in units of 1/cm3.
COMMENT: a second line.
UPDATED: 2012-10-11 17:53:43
COLUMNS: Energy (eV) | Cross section (m2)
-----------------------------
 3.5e-2\t0.0e+0
 4.0e-2\t1.7e-42
-----------------------------

IONIZATION
Fk -> Fk^+
 1.57e+1
PROCESS: E + Fk -> E + E + Fk+, Ionization
-----------------------------
 1.57e+1\t0.0e+0
 5.0e+1\t2.0e-20
-----------------------------
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
"""


def has_file(dataset_id: str) -> bool:
    entry = load_manifest()[dataset_id]
    return bool(entry.get("sha256")) and (REFERENCE_DIR / entry["path"]).is_file()


def real_data(dataset_id: str) -> pytest.MarkDecorator:
    return pytest.mark.skipif(not has_file(dataset_id), reason=f"{dataset_id} has not been downloaded here")


@pytest.fixture
def small_set(tmp_path: Path) -> Path:
    """A one-file data set with a correct manifest. Returns the manifest's path."""
    data = tmp_path / "file.csv"
    data.write_text("a,b\n1,2\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"datasets": [
        {"id": "demo", "path": "file.csv", "sha256": sha256_of(data), "how_to_get": "run the set-up script"},
    ]}), encoding="utf-8")
    return manifest


# ------------------------------------------------------------------- checksums and event E6
def test_good_file_is_ok(small_set: Path) -> None:
    assert check_reference_data(small_set) == {"demo": DataStatus.OK}
    assert verified_path("demo", small_set).name == "file.csv"


def test_changed_file_is_corrupt_and_refused(small_set: Path) -> None:
    (small_set.parent / "file.csv").write_text("a,b\n1,3\n", encoding="utf-8")  # one digit changed
    assert check_reference_data(small_set) == {"demo": DataStatus.CORRUPT}
    with pytest.raises(ReferenceDataError) as error:
        verified_path("demo", small_set)
    assert error.value.status is DataStatus.CORRUPT


def test_absent_file_is_missing_and_says_how_to_get_it(small_set: Path) -> None:
    (small_set.parent / "file.csv").unlink()
    assert check_reference_data(small_set) == {"demo": DataStatus.MISSING}
    with pytest.raises(ReferenceDataError, match="run the set-up script"):
        verified_path("demo", small_set)


# ------------------------------------------------------------------- the manifest itself
def test_every_dataset_has_source_citation_and_location() -> None:
    entries = load_manifest()
    assert {"nist_ar_i", "nist_o_i", "nist_h_i", "lxcat_cross_sections", "diatomic_constants", "benchmarks"} <= set(entries)
    for name, entry in entries.items():
        for field in ("path", "source", "citation", "url"):
            assert entry.get(field), f"{name} has no {field}"


def test_files_that_may_not_be_redistributed_are_ignored_by_git() -> None:
    """LXCat does not authorise redistribution, so its files must never reach the public repo."""
    ignore = (MANIFEST_PATH.parents[2] / ".gitignore").read_text(encoding="utf-8")
    for name, entry in load_manifest().items():
        if not entry["in_repository"]:
            assert str(Path(entry["path"]).parent.as_posix()) in ignore, name


def test_tracked_files_match_their_checksums() -> None:
    statuses = check_reference_data()
    for name, entry in load_manifest().items():
        if entry["in_repository"]:
            assert statuses[name] is DataStatus.OK, name


# ------------------------------------------------------------------- parsers
def test_nist_parser_handles_wrappers_blanks_and_units(tmp_path: Path) -> None:
    path = tmp_path / "lines.csv"
    path.write_text(FAKE_NIST, encoding="utf-8")
    lines = read_nist_lines(path, "Fk I")
    assert lines.wavelength_nm.tolist() == [400.02, 500.0]  # sorted; Ritz used when no observed value
    assert lines.a_ki_per_s.tolist() == [1.0e6, 2.0e7]  # the row with no A value is dropped
    assert lines.upper_energy_ev[1] == pytest.approx(21000.0 * EV_PER_CM1)  # the ? mark is ignored
    assert lines.g_upper.tolist() == [3, 5]


def test_cm1_to_ev_uses_the_right_factor() -> None:
    assert 1 / EV_PER_CM1 == pytest.approx(8065.544, abs=0.001)


def test_lxcat_parser_reads_every_block(tmp_path: Path) -> None:
    path = tmp_path / "cs.txt"
    path.write_text(FAKE_LXCAT, encoding="utf-8")
    elastic, excitation, attachment, ionization = read_lxcat(path)
    assert (elastic.process_type, elastic.target, elastic.threshold_ev) == ("ELASTIC", "Fk", 0.0)  # mass ratio skipped
    assert elastic.comments == ("elastic momentum transfer.",)
    assert (excitation.product, excitation.threshold_ev) == ("Fk(1S5)", 11.5)
    assert (attachment.process_type, attachment.product, attachment.threshold_ev) == ("ATTACHMENT", "Fk^-", 0.0)
    assert len(attachment.comments) == 2 and "normalized to gas density" in attachment.comments[0]
    assert attachment.energy_ev.tolist() == [0.035, 0.04]  # no threshold line, so the table starts at once
    assert ionization.threshold_ev == 15.7
    assert ionization.energy_ev.tolist() == [15.7, 50.0]
    assert ionization.sigma_m2[1] == 2.0e-20


# ------------------------------------------------------------------- spot values in real files
@real_data("nist_ar_i")
@pytest.mark.parametrize(("wavelength", "a_value", "g_upper"), [
    (811.531, 3.3e7, 7),  # NIST ASD 5.12 values
    (763.511, 2.45e7, 5),
    (750.387, 4.5e7, 1),
])
def test_argon_lines_have_the_published_values(wavelength: float, a_value: float, g_upper: int) -> None:
    lines = load_atomic_lines("Ar I")
    i = int(np.argmin(np.abs(lines.wavelength_nm - wavelength)))
    assert lines.wavelength_nm[i] == pytest.approx(wavelength, abs=0.01)
    assert lines.a_ki_per_s[i] == pytest.approx(a_value, rel=1e-6)
    assert lines.g_upper[i] == g_upper


@real_data("nist_ar_i")
def test_argon_2p_energies_are_physical() -> None:
    lines = load_atomic_lines("Ar I")
    i = int(np.argmin(np.abs(lines.wavelength_nm - 811.531)))
    assert lines.upper_energy_ev[i] == pytest.approx(13.08, abs=0.01)  # Ar 2p9
    assert lines.lower_energy_ev[i] == pytest.approx(11.55, abs=0.01)  # Ar 1s5 metastable


@real_data("nist_o_i")
def test_oxygen_triplet_is_present() -> None:
    lines = load_atomic_lines("O I")
    assert np.min(np.abs(lines.wavelength_nm - 777.194)) < 0.01
    assert np.min(np.abs(lines.wavelength_nm - 844.636)) < 0.02


@real_data("nist_h_i")
def test_h_alpha_is_present() -> None:
    lines = load_atomic_lines("H I")
    assert np.min(np.abs(lines.wavelength_nm - 656.28)) < 0.01


@real_data("lxcat_cross_sections")
def test_argon_cross_sections_have_the_right_threshold() -> None:
    sections = load_cross_sections("Ar")
    ionization = [s for s in sections if s.process_type == "IONIZATION"]
    assert ionization, "No argon ionization process in the file"
    assert ionization[0].threshold_ev == pytest.approx(15.76, abs=0.05)
    assert any(s.process_type in ("ELASTIC", "EFFECTIVE") for s in sections)
    assert any(s.process_type == "EXCITATION" for s in sections)


@real_data("lxcat_cross_sections")
@pytest.mark.parametrize(("gas", "ionization_ev"), [("Ar", 15.76), ("N2", 15.58), ("O2", 12.07)])
def test_every_gas_has_a_complete_set(gas: str, ionization_ev: float) -> None:
    """A Boltzmann solver needs elastic, excitation and ionization for each gas (published thresholds)."""
    sections = load_cross_sections(gas)
    kinds = {s.process_type for s in sections}
    assert {"ELASTIC", "EXCITATION", "IONIZATION"} <= kinds
    ionization = next(s for s in sections if s.process_type == "IONIZATION")
    assert ionization.threshold_ev == pytest.approx(ionization_ev, abs=0.02)
    for s in sections:
        assert np.all(np.diff(s.energy_ev) >= 0) and np.all(s.sigma_m2 >= 0), s.description


@real_data("lxcat_cross_sections")
def test_argon_shows_the_ramsauer_minimum() -> None:
    """Independent physics check: argon's elastic cross-section has a deep dip near 0.25 eV."""
    elastic = next(s for s in load_cross_sections("Ar") if s.process_type == "ELASTIC")
    low = elastic.energy_ev < 2.0
    minimum_at = elastic.energy_ev[low][np.argmin(elastic.sigma_m2[low])]
    assert 0.15 < minimum_at < 0.4
    assert elastic.sigma_m2[low].min() < 0.1 * elastic.sigma_m2[0]


@real_data("lxcat_cross_sections")
def test_three_body_attachment_carries_its_unit_warning() -> None:
    """The O2 three-body sigma is scaled by gas density, so the physics code must be able to see that."""
    three_body = next(s for s in load_cross_sections("O2") if s.description.startswith("E + O2 -> O2-"))
    assert any("normalized to gas density" in c for c in three_body.comments)


# ------------------------------------------------------------------- constants and benchmarks
def test_n2_constants_give_the_known_337_nm_band() -> None:
    """Independent check on the transcription: C-B (0,0) must fall at about 337 nm."""
    c = load_diatomic_constants("N2", "C3Pi_u")
    b = load_diatomic_constants("N2", "B3Pi_g")
    assert b["Te_cm1"] < c["Te_cm1"]

    def zero_point(state: dict) -> float:
        return state["we_cm1"] / 2 - state["wexe_cm1"] / 4

    band_origin = (c["Te_cm1"] + zero_point(c)) - (b["Te_cm1"] + zero_point(b))
    assert 1e7 / band_origin == pytest.approx(337.0, abs=0.3)


def test_oh_constants_give_the_known_309_nm_band() -> None:
    a = load_diatomic_constants("OH", "A2Sigma+")
    x = load_diatomic_constants("OH", "X2Pi")

    def zero_point(state: dict) -> float:
        return state["we_cm1"] / 2 - state["wexe_cm1"] / 4

    band_origin = (a["Te_cm1"] + zero_point(a)) - (x["Te_cm1"] + zero_point(x))
    assert 1e7 / band_origin == pytest.approx(308.0, abs=2.0)


def test_every_benchmark_row_has_a_citation() -> None:
    for row in load_benchmarks():
        assert row["citation"].strip(), row
        assert row["location_in_source"].strip(), row


@real_data("lxcat_bsr_argon")
def test_bsr_has_collisions_from_every_1s_level() -> None:
    """The CR model needs excitation from each 1s level up to the 2p levels (Phase 4)."""
    from plasma_twin.reference.loaders import load_bsr_argon
    sections = load_bsr_argon()
    targets = {s.target for s in sections}
    assert {"Ar", "Ar(4s[3/2]2)", "Ar(4s[3/2]1)", "Ar(4s'[1/2]0)", "Ar(4s'[1/2]1)"} <= targets
    from_1s5 = {s.product for s in sections if s.target == "Ar(4s[3/2]2)" and s.process_type == "EXCITATION"}
    assert "Ar(4p[1/2]1)" in from_1s5  # 2p10, the lowest 2p level
    ground_labels = {s.product for s in sections if s.target == "Ar" and s.process_type == "EXCITATION"}
    assert "Ar(4s[3/2]2, 3P2, 1s5)" in ground_labels  # the file itself pairs Racah and Paschen names
