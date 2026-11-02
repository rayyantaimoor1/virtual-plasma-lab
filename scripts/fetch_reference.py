"""Set-up tool: download NIST line data, register LXCat files, and record checksums.

This is the ONLY project code that goes online, and it runs once during set-up, never inside the
application (SEC-5, OE-4).

  python scripts/fetch_reference.py nist            download NIST lines into data/reference/nist/
  python scripts/fetch_reference.py nist --record   same, and record their checksums as the reference
  python scripts/fetch_reference.py lxcat FILE      copy your LXCat (Biagi) download in and record its checksum
  python scripts/fetch_reference.py lxcat FILE --dataset lxcat_bsr_argon   the same for the BSR argon file
  python scripts/fetch_reference.py record-tracked  record checksums of files kept in the repository
  python scripts/fetch_reference.py status          show the state of every data set

Without --record, a teammate's download is compared with the recorded checksum, so a change in
NIST's data shows up as a mismatch instead of silently changing the physics.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plasma_twin.reference.loaders import MANIFEST_PATH, REFERENCE_DIR, check_reference_data, load_manifest, sha256_of  # noqa: E402

NIST_URL = "https://physics.nist.gov/cgi-bin/ASD/lines1.pl"
# Wavelength windows cover the OES range in envelope.toml and the lines the SRS names.
NIST_REQUESTS = {
    "nist_ar_i": ("Ar I", 300, 1000),
    "nist_o_i": ("O I", 300, 1000),
    "nist_h_i": ("H I", 300, 1000),
    # Infrared 2p -> 1s argon lines (for example 2p10 -> 1s3 near 1047 nm): needed so the CR model
    # (Phase 4) includes every decay route of the 2p levels, not only the visible ones.
    "nist_ar_i_ir": ("Ar I", 1000, 1400),
}


def download_nist(spectrum: str, low_nm: int, high_nm: int) -> bytes:
    """Request one spectrum from NIST ASD as CSV, with air wavelengths and level energies in cm^-1."""
    query = urllib.parse.urlencode({
        "spectra": spectrum, "low_w": low_nm, "upp_w": high_nm, "unit": 1, "format": 2,
        "show_obs_wl": 1, "show_calc_wl": 1, "order_out": 0, "show_av": 2, "A_out": 0,
        "allowed_out": 1, "forbid_out": 1, "enrg_out": "on", "g_out": "on", "term_out": "on",
        "conf_out": "on", "submit": "Retrieve Data",
    })
    # NIST refuses Python's default identifier, so name this tool honestly instead.
    request = urllib.request.Request(f"{NIST_URL}?{query}", headers={"User-Agent": "virtual-plasma-lab-setup/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    if not data.startswith(b"obs_wl_air"):
        raise RuntimeError(f"NIST did not return CSV for {spectrum}: {data[:200]!r}")
    return data


def write_manifest(updates: dict[str, dict[str, str]]) -> None:
    """Apply field updates to manifest entries, keeping their order."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for entry in manifest["datasets"]:
        entry.update(updates.get(entry["id"], {}))
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def fetch_nist(record: bool) -> None:
    entries = load_manifest()
    updates: dict[str, dict[str, str]] = {}
    for dataset_id, (spectrum, low, high) in NIST_REQUESTS.items():
        path = REFERENCE_DIR / entries[dataset_id]["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(download_nist(spectrum, low, high))
        print(f"{spectrum}: {path.stat().st_size} bytes")
        if record:
            updates[dataset_id] = {"sha256": sha256_of(path), "retrieved": date.today().isoformat()}
    if record:
        write_manifest(updates)


def register_lxcat(source: Path, dataset_id: str = "lxcat_cross_sections") -> None:
    entry = load_manifest()[dataset_id]
    target = REFERENCE_DIR / entry["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    write_manifest({dataset_id: {"sha256": sha256_of(target), "retrieved": date.today().isoformat()}})
    print(f"Registered {target.name}. Now tell Claude, so the citation can be read from the file header.")


def record_tracked() -> None:
    """Record checksums of the files kept in the repository, after one is deliberately edited."""
    updates = {name: {"sha256": sha256_of(REFERENCE_DIR / entry["path"])}
               for name, entry in load_manifest().items() if entry["in_repository"]}
    write_manifest(updates)


def show_status() -> None:
    for name, status in check_reference_data().items():
        print(f"{name:24} {status.value}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    nist = commands.add_parser("nist")
    nist.add_argument("--record", action="store_true")
    lxcat = commands.add_parser("lxcat")
    lxcat.add_argument("file", type=Path)
    lxcat.add_argument("--dataset", default="lxcat_cross_sections")
    commands.add_parser("status")
    commands.add_parser("record-tracked")
    args = parser.parse_args()
    if args.command == "nist":
        fetch_nist(args.record)
    elif args.command == "lxcat":
        register_lxcat(args.file, args.dataset)
    elif args.command == "record-tracked":
        record_tracked()
    show_status()


if __name__ == "__main__":
    main()
