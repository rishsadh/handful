"""Dataset acquisition gate.

This module never downloads anything. Kaggle downloads require the user's own
authenticated session, and an unofficial mirror is not an acceptable substitute for the
selected release. What it does is record provenance and refuse to let the pipeline
proceed on an unidentified dataset.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from foodcom.utils import logging as flog
from foodcom.utils.config import UNRECORDED, Configs
from foodcom.utils.hashing import sha256_file

log = flog.get_logger(__name__)

DOWNLOAD_INSTRUCTIONS = """\
The two raw files are not present and cannot be fetched automatically.

  1. Sign in to Kaggle and open:
     https://www.kaggle.com/datasets/shuyangli94/food-com-recipes-and-user-interactions
  2. Note the dataset VERSION number shown on the page, and copy the LICENCE wording
     exactly as Kaggle states it.
  3. Download the archive and place these two files, unmodified, in `data/raw/`:
       RAW_recipes.csv
       RAW_interactions.csv
  4. Fill in `config/research.yaml` -> dataset.kaggle_version, dataset.download_date and
     dataset.licence_text. Set dataset.licence_permits_redistribution only if the licence
     actually says so.
  5. Re-run `python tasks.py acquire`.

Do not substitute another uploader's copy, a prefiltered classroom subset, or a mirror.
"""


class AcquisitionError(RuntimeError):
    """Raised when the data gate cannot be passed."""


@dataclass
class FileRecord:
    filename: str
    present: bool
    bytes: int | None = None
    sha256: str | None = None
    modified_utc: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "present": self.present,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "modified_utc": self.modified_utc,
        }


@dataclass
class SourceManifest:
    dataset_name: str
    uploader: str
    source_url: str
    kaggle_version: str
    download_date: str
    licence_text: str
    licence_permits_redistribution: bool | None
    recorded_utc: str
    files: list[FileRecord] = field(default_factory=list)
    protocol_version: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "uploader": self.uploader,
            "source_url": self.source_url,
            "kaggle_version": self.kaggle_version,
            "download_date": self.download_date,
            "licence_text": self.licence_text,
            "licence_permits_redistribution": self.licence_permits_redistribution,
            "recorded_utc": self.recorded_utc,
            "protocol_version": self.protocol_version,
            "files": [f.as_dict() for f in self.files],
            "note": (
                "Raw bytes are immutable. Every transformation writes to data/interim or "
                "data/processed. Counts published in the source paper describe its filtered "
                "task corpus and are not our counts."
            ),
        }


def inspect_raw_files(cfg: Configs) -> list[FileRecord]:
    """Hash and size whichever required files are present."""
    raw_dir = cfg.path("raw_dir")
    records: list[FileRecord] = []
    for filename in cfg.research.dataset.required_files:
        p = raw_dir / filename
        if p.exists():
            stat = p.stat()
            records.append(
                FileRecord(
                    filename=filename,
                    present=True,
                    bytes=stat.st_size,
                    sha256=sha256_file(p),
                    modified_utc=dt.datetime.fromtimestamp(
                        stat.st_mtime, tz=dt.UTC
                    ).isoformat(),
                )
            )
        else:
            records.append(FileRecord(filename=filename, present=False))
    return records


def missing_files(cfg: Configs) -> list[str]:
    return [r.filename for r in inspect_raw_files(cfg) if not r.present]


def build_source_manifest(cfg: Configs, *, strict: bool = True) -> SourceManifest:
    """Assemble the provenance record, refusing to certify an unidentified dataset.

    `strict=False` still builds the manifest but marks it incomplete - used by the demo
    and audit so they can report the gate status rather than crash.
    """
    ds = cfg.research.dataset
    records = inspect_raw_files(cfg)
    absent = [r.filename for r in records if not r.present]

    if strict and absent:
        raise AcquisitionError(
            "Data gate not passed - missing raw files: "
            + ", ".join(absent)
            + f"\n\nExpected in: {cfg.path('raw_dir')}\n\n"
            + DOWNLOAD_INSTRUCTIONS
        )

    if strict and not ds.provenance_complete:
        raise AcquisitionError(
            "Data gate not passed - provenance still UNRECORDED for: "
            + ", ".join(ds.missing_provenance_fields())
            + "\n\nFill these in `config/research.yaml` from the Kaggle dataset page. "
            "A dataset we cannot name a version and licence for is not a citable source."
        )

    return SourceManifest(
        dataset_name=ds.name,
        uploader=ds.uploader,
        source_url=ds.source_url,
        kaggle_version=ds.kaggle_version,
        download_date=ds.download_date,
        licence_text=ds.licence_text,
        licence_permits_redistribution=ds.licence_permits_redistribution,
        recorded_utc=dt.datetime.now(dt.UTC).isoformat(),
        files=records,
        protocol_version=cfg.research.protocol_version,
    )


def redistribution_allowed(cfg: Configs) -> bool:
    """Whether raw data or review text may be bundled anywhere outward-facing.

    `None` (unknown) is treated as "no". Permission has to be established, not assumed
    from a repository licence that covers code rather than data.
    """
    return cfg.research.dataset.licence_permits_redistribution is True


def gate_status(cfg: Configs) -> dict[str, Any]:
    """A structured report of the data gate, safe to call when nothing is present."""
    records = inspect_raw_files(cfg)
    ds = cfg.research.dataset
    absent = [r.filename for r in records if not r.present]
    return {
        "files_present": not absent,
        "missing_files": absent,
        "provenance_complete": ds.provenance_complete,
        "missing_provenance_fields": ds.missing_provenance_fields(),
        "redistribution_allowed": redistribution_allowed(cfg),
        "passed": (not absent) and ds.provenance_complete,
        "raw_dir": str(cfg.path("raw_dir")),
        "instructions": DOWNLOAD_INSTRUCTIONS if absent or not ds.provenance_complete else None,
    }


def write_source_manifest(cfg: Configs, out_path: Path | None = None) -> Path:
    manifest = build_source_manifest(cfg, strict=True)
    out = out_path or (cfg.path("processed_dir") / "source_manifest.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    import json

    out.write_text(json.dumps(manifest.as_dict(), indent=2), encoding="utf-8")
    log.info("source manifest written to %s", out)
    return out


def assert_unrecorded_placeholders_absent(cfg: Configs) -> None:
    """Guard used before any final run: no placeholder may survive into published results."""
    ds = cfg.research.dataset
    bad = [f for f in ("kaggle_version", "download_date", "licence_text")
           if getattr(ds, f) == UNRECORDED]
    if bad:
        raise AcquisitionError(f"provenance fields still UNRECORDED: {bad}")
