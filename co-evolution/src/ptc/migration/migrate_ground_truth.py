"""
migrate_ground_truth.py
-----------------------
Migrate t2p-ground-truth CSVs for legacy experiments (tctracer-2020,
tctracer-2022, testlinker) to the canonical column layout used by t2plinker:

    project, from_name, to_name, from_url, to_url,
    from_fqs, from_tctracer_fqs, from_testlinker_fqs,
    to_fqs, to_tctracer_fqs, to_testlinker_fqs,
    from_artifact, to_artifact, to_call_depth,
    label, tags, notes

The three new data columns are resolved from sibling experiment artefacts:

    - from_artifact / to_artifact
        workspace/experiment/{exp}/method/{project}.csv
        joined on (project, url)

    - to_call_depth
        workspace/experiment/{exp}/t2p-candidate-expanded/{project}.csv
        joined on (project, from_url, to_url)

Fixed values:
    - label  = 1
    - tags   = "" (null)
    - notes  = "" (null)

Usage
-----
    python migrate_ground_truth.py [--dry-run] [--experiments e1,e2]

Environment variables (read via python-dotenv from .env in project root):
    WORKSPACE_DIRECTORY             root of the workspace (contains workspace/ and data/)
    ME_EVALUATION_EXPERIMENTS_NAMES comma-separated experiment names to migrate
                                    default: tctracer-2020,tctracer-2022,testlinker
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Optional dotenv support  (must run before reading any env vars)
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on real environment variables

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TARGET_COLUMNS = [
    "project",
    "from_name",
    "to_name",
    "from_url",
    "to_url",
    "from_fqs",
    "from_tctracer_fqs",
    "from_testlinker_fqs",
    "to_fqs",
    "to_tctracer_fqs",
    "to_testlinker_fqs",
    "from_artifact",
    "to_artifact",
    "to_call_depth",
    "label",
    "tags",
    "notes",
]

# Columns that must already exist in the source ground-truth file
SOURCE_REQUIRED_COLUMNS = [
    "project",
    "from_name",
    "to_name",
    "from_url",
    "to_url",
    "from_fqs",
    "from_tctracer_fqs",
    "from_testlinker_fqs",
    "to_fqs",
    "to_tctracer_fqs",
    "to_testlinker_fqs",
]

DEFAULT_EXPERIMENTS = ["tctracer-2020", "tctracer-2022", "testlinker"]

# ---------------------------------------------------------------------------
# Lookup table helpers
# ---------------------------------------------------------------------------

MethodKey = Tuple[str, str]  # (project, url)
CandKey = Tuple[str, str, str]  # (project, from_url, to_url)


def _load_method_index(method_csv: Path) -> Dict[MethodKey, str]:
    """Return {(project, url): artifact} from a method CSV."""
    index: Dict[MethodKey, str] = {}
    if not method_csv.exists():
        logger.warning("Method CSV not found: %s", method_csv)
        return index
    with method_csv.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key: MethodKey = (row["project"], row["url"])
            index[key] = row.get("artifact", "")
    logger.debug("Loaded %d method entries from %s", len(index), method_csv.name)
    return index


def _load_candidate_index(cand_csv: Path) -> Dict[CandKey, str]:
    """Return {(project, from_url, to_url): to_call_depth} from a candidate-expanded CSV."""
    index: Dict[CandKey, str] = {}
    if not cand_csv.exists():
        logger.warning("Candidate-expanded CSV not found: %s", cand_csv)
        return index
    with cand_csv.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key: CandKey = (row["project"], row["from_url"], row["to_url"])
            # Keep the first match (should be unique per pair, but be safe)
            if key not in index:
                index[key] = row.get("to_call_depth", "")
    logger.debug("Loaded %d candidate entries from %s", len(index), cand_csv.name)
    return index


# ---------------------------------------------------------------------------
# Core migration logic
# ---------------------------------------------------------------------------


def migrate_project_csv(
    gt_csv: Path,
    method_index: Dict[MethodKey, str],
    cand_index: Dict[CandKey, str],
    dry_run: bool = False,
) -> dict:
    """
    Enrich a single ground-truth CSV with the missing columns and overwrite it
    in place (unless *dry_run* is True).

    Returns a stats dict: {total, already_migrated, enriched, missing_cand, missing_method}.
    """
    stats = {
        "total": 0,
        "already_migrated": 0,
        "enriched": 0,
        "missing_cand": 0,
        "missing_method_from": 0,
        "missing_method_to": 0,
    }

    rows: list[dict] = []
    with gt_csv.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        existing_cols = reader.fieldnames or []

        # Validate required source columns
        missing_src = [c for c in SOURCE_REQUIRED_COLUMNS if c not in existing_cols]
        if missing_src:
            raise ValueError(
                f"{gt_csv}: missing required source columns: {missing_src}"
            )

        # Skip files that are already in the target format (idempotency)
        if set(TARGET_COLUMNS).issubset(set(existing_cols)):
            logger.info("Already migrated (skipping): %s", gt_csv)
            stats["already_migrated"] = sum(1 for _ in reader)
            return stats

        for row in reader:
            stats["total"] += 1
            project = row["project"]

            # --- artifact lookup ---
            from_artifact = method_index.get((project, row["from_url"]), "")
            to_artifact = method_index.get((project, row["to_url"]), "")
            if not from_artifact:
                stats["missing_method_from"] += 1
            if not to_artifact:
                stats["missing_method_to"] += 1

            # --- to_call_depth lookup ---
            cand_key: CandKey = (project, row["from_url"], row["to_url"])
            to_call_depth = cand_index.get(cand_key, "")
            if to_call_depth == "":
                stats["missing_cand"] += 1

            out_row = {
                "project": project,
                "from_name": row["from_name"],
                "to_name": row["to_name"],
                "from_url": row["from_url"],
                "to_url": row["to_url"],
                "from_fqs": row["from_fqs"],
                "from_tctracer_fqs": row["from_tctracer_fqs"],
                "from_testlinker_fqs": row["from_testlinker_fqs"],
                "to_fqs": row["to_fqs"],
                "to_tctracer_fqs": row["to_tctracer_fqs"],
                "to_testlinker_fqs": row["to_testlinker_fqs"],
                "from_artifact": from_artifact,
                "to_artifact": to_artifact,
                "to_call_depth": to_call_depth,
                "label": 1,
                "tags": "",
                "notes": "",
            }
            rows.append(out_row)
            stats["enriched"] += 1

    if not dry_run:
        with gt_csv.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=TARGET_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        logger.info("Written %d rows → %s", len(rows), gt_csv)
    else:
        logger.info("[dry-run] Would write %d rows → %s", len(rows), gt_csv)

    return stats


def migrate_experiment(
    project_dir: Path,
    workspace_dir: Path,
    experiment: str,
    dry_run: bool = False,
) -> None:
    """Migrate all project CSVs for one experiment."""
    gt_dir = project_dir / "data" / experiment / "t2p-ground-truth"
    method_dir = workspace_dir / "experiment" / experiment / "method"
    cand_dir = workspace_dir / "experiment" / experiment / "t2p-candidate-expanded"

    if not gt_dir.exists():
        logger.warning("Ground-truth directory not found for %s: %s", experiment, gt_dir)
        return

    gt_csvs = sorted(gt_dir.glob("*.csv"))
    if not gt_csvs:
        logger.warning("No CSV files in %s", gt_dir)
        return

    logger.info("=== %s  (%d project(s)) ===", experiment, len(gt_csvs))

    for gt_csv in gt_csvs:
        project = gt_csv.stem
        method_index = _load_method_index(method_dir / f"{project}.csv")
        cand_index = _load_candidate_index(cand_dir / f"{project}.csv")

        try:
            stats = migrate_project_csv(gt_csv, method_index, cand_index, dry_run=dry_run)
        except Exception as exc:
            logger.error("Failed to migrate %s: %s", gt_csv, exc)
            continue

        if stats.get("already_migrated"):
            logger.info(
                "  %-30s  already migrated (%d rows)",
                project,
                stats["already_migrated"],
            )
        else:
            logger.info(
                "  %-30s  total=%d  enriched=%d  "
                "missing_cand=%d  missing_method_from=%d  missing_method_to=%d",
                project,
                stats["total"],
                stats["enriched"],
                stats["missing_cand"],
                stats["missing_method_from"],
                stats["missing_method_to"],
            )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate t2p-ground-truth CSVs to the canonical t2plinker column layout."
        )
    )
    parser.add_argument(
        "--workspace-directory",
        default=os.getenv("ME_WORKSPACE_DIRECTORY"),
        help="Workspace subdirectory (contains experiment/). "
        "Defaults to $ME_WORKSPACE_DIRECTORY.",
    )
    parser.add_argument(
        "--project-directory",
        default=os.getenv("ME_PROJECT_DIRECTORY"),
        help="Project root directory (contains data/). "
        "Defaults to $ME_PROJECT_DIRECTORY.",
    )
    parser.add_argument(
        "--experiments",
        default=os.getenv("ME_EVALUATION_EXPERIMENTS_NAMES"),
        help="Comma-separated list of experiment names to migrate. "
        "Defaults to $ME_EVALUATION_EXPERIMENTS_NAMES or "
        f"{','.join(DEFAULT_EXPERIMENTS)}.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without writing any files.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = _parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(message)s",
        stream=sys.stdout,
    )

    # Resolve workspace directory
    workspace_dir_str = args.workspace_directory
    if not workspace_dir_str:
        logger.error(
            "Workspace directory not specified. "
            "Use --workspace-directory or set $WORKSPACE_DIRECTORY."
        )
        sys.exit(1)
    workspace_dir = Path(workspace_dir_str).expanduser().resolve()
    if not workspace_dir.is_dir():
        logger.error("Workspace directory does not exist: %s", workspace_dir)
        sys.exit(1)

    project_dir_str = args.project_directory
    if not project_dir_str:
        logger.error(
            "Project directory not specified. "
            "Use --project-directory or set $ME_PROJECT_DIRECTORY."
        )
        sys.exit(1)
    project_dir = Path(project_dir_str).expanduser().resolve()
    if not project_dir.is_dir():
        logger.error("Project directory does not exist: %s", project_dir)
        sys.exit(1)
    # Resolve experiment list
    if args.experiments:
        experiments = [e.strip() for e in args.experiments.split(",") if e.strip()]
    else:
        experiments = DEFAULT_EXPERIMENTS
        logger.info(
            "No experiments specified; using defaults: %s", ", ".join(experiments)
        )

    if args.dry_run:
        logger.info("*** DRY-RUN MODE — no files will be written ***")

    for experiment in experiments:
        migrate_experiment(project_dir, workspace_dir, experiment, dry_run=args.dry_run)

    logger.info("Done.")


if __name__ == "__main__":
    main()
