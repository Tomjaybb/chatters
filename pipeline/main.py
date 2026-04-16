"""CLI entry point — wires all pipeline stages together.

Usage:
    python -m pipeline run --agencies agencies.csv
    python -m pipeline run --agencies agencies.csv --single-agency some_handle
    python -m pipeline run --agencies agencies.csv --dry-run
    python -m pipeline export
    python -m pipeline stats
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import click
from loguru import logger

from pipeline.aggregator_scraper import scrape_aggregator_page
from pipeline.config import Config, load_config
from pipeline.database import Database
from pipeline.exporter import export_all
from pipeline.instagram_scraper import get_provider, scrape_agency_following
from pipeline.keyword_detector import detect_keywords
from pipeline.subscription_detector import detect_platforms


def _setup_logging(cfg: Config) -> None:
    """Configure loguru to log to console + rotating file."""
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}",
    )
    logger.add(
        str(cfg.log_path),
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        compression="gz",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | {name}:{function}:{line} | {message}",
    )


def _load_agencies_csv(path: Path) -> list[dict[str, str]]:
    """Read the agency seed CSV and return a list of row dicts."""
    if not path.exists():
        logger.error("Agency CSV not found: {}", path)
        sys.exit(1)
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    logger.info("Loaded {} agencies from {}", len(rows), path)
    return rows


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

def stage_1_ingest(db: Database, csv_path: Path) -> list[dict[str, str]]:
    """Stage 1: Read agency CSV and upsert into database."""
    agencies = _load_agencies_csv(csv_path)
    for row in agencies:
        db.upsert_agency(
            agency_name=row.get("agency_name", ""),
            instagram_handle=row.get("instagram_handle", ""),
            country=row.get("country", ""),
            notes=row.get("notes", ""),
        )
    logger.info("Stage 1 complete — {} agencies ingested", len(agencies))
    return agencies


def stage_2_scrape_ig(
    db: Database,
    agencies: list[dict[str, str]],
    cfg: Config,
) -> int:
    """Stage 2: For each agency, scrape their following list."""
    provider = get_provider(cfg.ig_provider)
    provider.login(cfg)

    total_found = 0

    for row in agencies:
        handle = row.get("instagram_handle", "").lower().strip("@")
        if not handle:
            continue

        if cfg.single_agency and handle != cfg.single_agency.lower().strip("@"):
            continue

        # Check if already scraped (cache hit)
        existing = db.conn.execute(
            "SELECT last_scraped_at FROM agencies WHERE instagram_handle = ?",
            (handle,),
        ).fetchone()
        if existing and existing["last_scraped_at"] and not cfg.single_agency:
            logger.info("Skipping @{} — already scraped", handle)
            continue

        profiles = scrape_agency_following(handle, cfg, provider=provider)

        for p in profiles:
            db.upsert_followed_account({
                "username": p.username,
                "display_name": p.display_name,
                "follower_count": p.follower_count,
                "bio_text": p.bio_text,
                "bio_link": p.bio_link,
                "profile_pic_url": p.profile_pic_url,
                "is_verified": p.is_verified,
                "is_business": p.is_business,
                "discovered_via_agency": handle,
            })
            db.link_agency_follow(handle, p.username)

        db.mark_agency_scraped(handle)
        total_found += len(profiles)
        logger.info(
            "Stage 2 — @{}: {} accounts recorded (checkpoint saved)", handle, len(profiles)
        )

    logger.info("Stage 2 complete — {} total followed accounts found", total_found)
    return total_found


def stages_3_4_5_6_process(db: Database, cfg: Config) -> int:
    """Stages 3-6: For accounts with bio links, scrape aggregator pages,
    detect subscription platforms, and run keyword analysis."""
    accounts = db.get_accounts_needing_scrape()
    logger.info("Stage 3-6 — {} accounts to process", len(accounts))

    processed = 0
    for acct in accounts:
        username = acct["username"]
        bio_link = acct["bio_link"]

        if not bio_link:
            continue

        # Stage 3+4: Scrape aggregator page
        result = scrape_aggregator_page(bio_link, cfg)

        page_id = db.insert_aggregator_page(
            account_username=username,
            source_url=bio_link,
            aggregator_type=result.aggregator_type,
            bio_text=result.bio_text,
            page_text=result.page_text,
            error=result.error,
        )

        if result.error:
            logger.warning("  {} — scrape error: {}", username, result.error)
            continue

        # Stage 5: Check all extracted links for subscription platforms
        all_urls = [link.url for link in result.links]
        platform_matches = detect_platforms(all_urls)

        for link in result.links:
            from pipeline.subscription_detector import detect_platform
            pm = detect_platform(link.url)
            db.insert_detected_link(
                aggregator_page_id=page_id,
                url=link.url,
                title=link.title,
                description=link.description,
                is_subscription=pm is not None,
                platform_name=pm.platform_name if pm else "",
                platform_username=pm.username or "" if pm else "",
            )

        has_sub = len(platform_matches) > 0

        # Stage 6: Keyword detection across all text
        texts = [result.bio_text, result.page_text]
        texts.extend(link.title for link in result.links)
        texts.extend(link.description for link in result.links)
        texts = [t for t in texts if t]

        kw_result = detect_keywords(texts, has_subscription_link=has_sub)

        for m in kw_result.matches:
            db.insert_keyword_match(
                account_username=username,
                keyword=m.keyword,
                category=m.category,
                context=m.context,
            )

        # Determine status
        if has_sub:
            status = "confirmed"
        elif kw_result.confidence_score >= 50:
            status = "likely_paid_creator"
        elif kw_result.confidence_score >= 40:
            status = "review_queue"
        else:
            status = "unlikely"

        sub_platforms = ", ".join(pm.platform_name for pm in platform_matches)
        sub_urls = ", ".join(pm.url for pm in platform_matches)
        kw_list = ", ".join(kw_result.matched_keywords)

        db.upsert_confidence(
            account_username=username,
            score=kw_result.confidence_score,
            status=status,
            subscription_platforms=sub_platforms,
            subscription_urls=sub_urls,
            adult_keywords=kw_list,
        )

        processed += 1
        logger.debug(
            "  {} — score={} status={} platforms=[{}]",
            username, kw_result.confidence_score, status, sub_platforms,
        )

    logger.info("Stages 3-6 complete — {} accounts processed", processed)
    return processed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
@click.option("--env-file", default=".env", help="Path to .env config file")
@click.pass_context
def cli(ctx: click.Context, env_file: str) -> None:
    """Cleaner.io Creator Discovery Pipeline"""
    ctx.ensure_object(dict)
    ctx.obj["env_file"] = env_file


@cli.command()
@click.option("--agencies", required=True, type=click.Path(exists=True), help="Path to agency CSV")
@click.option("--dry-run", is_flag=True, help="Show what would be done without scraping")
@click.option("--single-agency", default=None, help="Only process this one agency handle")
@click.option("--provider", default="instaloader", type=click.Choice(["instaloader", "apify", "instagrapi"]))
@click.option("--skip-ig", is_flag=True, help="Skip Instagram scraping (process existing data only)")
@click.pass_context
def run(
    ctx: click.Context,
    agencies: str,
    dry_run: bool,
    single_agency: str | None,
    provider: str,
    skip_ig: bool,
) -> None:
    """Run the full discovery pipeline."""
    cfg = load_config(
        ctx.obj["env_file"],
        dry_run=dry_run,
        single_agency=single_agency,
        ig_provider=provider,
    )
    _setup_logging(cfg)
    logger.info("Pipeline starting (dry_run={}, provider={})", dry_run, provider)

    db = Database(cfg.db_path)
    db.connect()

    try:
        # Stage 1
        agency_rows = stage_1_ingest(db, Path(agencies))

        # Stage 2
        if not skip_ig:
            stage_2_scrape_ig(db, agency_rows, cfg)
        else:
            logger.info("Skipping Instagram scraping (--skip-ig)")

        # Stages 3-6
        stages_3_4_5_6_process(db, cfg)

        # Stage 7: Export
        paths = export_all(db, cfg.output_dir)
        logger.info("Exports written:")
        for name, path in paths.items():
            logger.info("  {}: {}", name, path)

        # Maintenance
        db.purge_stale(cfg.retention_days)

        # Summary
        stats = db.stats()
        logger.info("Pipeline complete. DB stats: {}", stats)

    finally:
        db.close()


@cli.command()
@click.option("--min-score", default=0, help="Minimum confidence score to export")
@click.pass_context
def export(ctx: click.Context, min_score: int) -> None:
    """Export results to CSV without re-running the pipeline."""
    cfg = load_config(ctx.obj["env_file"])
    _setup_logging(cfg)

    db = Database(cfg.db_path)
    db.connect()
    try:
        paths = export_all(db, cfg.output_dir)
        for name, path in paths.items():
            click.echo(f"  {name}: {path}")
    finally:
        db.close()


@cli.command()
@click.pass_context
def stats(ctx: click.Context) -> None:
    """Show database statistics."""
    cfg = load_config(ctx.obj["env_file"])
    db = Database(cfg.db_path)
    db.connect()
    try:
        s = db.stats()
        click.echo("Database statistics:")
        for table, count in s.items():
            click.echo(f"  {table}: {count}")
    finally:
        db.close()


if __name__ == "__main__":
    cli()
