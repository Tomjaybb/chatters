"""Stage 7: CSV export and CRM-ready output generation."""

from __future__ import annotations

import csv
from pathlib import Path

from loguru import logger

from pipeline.database import Database

# Columns for the full export
FULL_COLUMNS = [
    "instagram_handle",
    "display_name",
    "follower_count",
    "bio_link",
    "aggregator_type",
    "subscription_platforms_found",
    "subscription_urls",
    "adult_keywords_matched",
    "confidence_score",
    "status",
    "discovered_via_agency",
    "last_checked_at",
]

# Columns for the confirmed-only export
CONFIRMED_COLUMNS = [
    "instagram_handle",
    "display_name",
    "follower_count",
    "subscription_platforms_found",
    "subscription_urls",
    "confidence_score",
    "discovered_via_agency",
]


def _write_csv(
    path: Path,
    rows: list[dict],
    columns: list[str],
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return len(rows)


def export_full(db: Database, output_dir: Path) -> Path:
    """Export all accounts with confidence scores to a CSV."""
    rows = db.export_rows(min_score=0)
    out_path = output_dir / "all_creators.csv"
    count = _write_csv(out_path, rows, FULL_COLUMNS)
    logger.info("Exported {} accounts to {}", count, out_path)
    return out_path


def export_confirmed(db: Database, output_dir: Path) -> Path:
    """Export only confirmed creators (score >= 80) ready for outreach."""
    rows = db.export_rows(min_score=80)
    out_path = output_dir / "confirmed_creators.csv"
    count = _write_csv(out_path, rows, CONFIRMED_COLUMNS)
    logger.info("Exported {} confirmed creators to {}", count, out_path)
    return out_path


def export_review_queue(db: Database, output_dir: Path) -> Path:
    """Export borderline accounts (score 40-60) for manual review."""
    all_rows = db.export_rows(min_score=40)
    rows = [r for r in all_rows if (r.get("confidence_score") or 0) <= 60]
    out_path = output_dir / "review_queue.csv"
    count = _write_csv(out_path, rows, FULL_COLUMNS)
    logger.info("Exported {} accounts to review queue at {}", count, out_path)
    return out_path


def export_all(db: Database, output_dir: Path) -> dict[str, Path]:
    """Run all exports and return a mapping of name → path."""
    return {
        "full": export_full(db, output_dir),
        "confirmed": export_confirmed(db, output_dir),
        "review_queue": export_review_queue(db, output_dir),
    }
