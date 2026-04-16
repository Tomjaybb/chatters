"""SQLite database layer for the creator discovery pipeline.

Stores agencies, followed accounts, aggregator pages, detected links,
keyword matches, and confidence scores.  Provides CRUD helpers and
a data-retention purge routine.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator

from loguru import logger

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agencies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agency_name     TEXT NOT NULL,
    instagram_handle TEXT NOT NULL UNIQUE,
    country         TEXT,
    notes           TEXT,
    last_scraped_at TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS followed_accounts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    username          TEXT NOT NULL,
    display_name      TEXT,
    follower_count    INTEGER,
    bio_text          TEXT,
    bio_link          TEXT,
    profile_pic_url   TEXT,
    is_verified       INTEGER DEFAULT 0,
    is_business       INTEGER DEFAULT 0,
    discovered_via_agency TEXT,
    last_checked_at   TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(username)
);

CREATE TABLE IF NOT EXISTS agency_follows (
    agency_handle   TEXT NOT NULL,
    account_username TEXT NOT NULL,
    discovered_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (agency_handle, account_username)
);

CREATE TABLE IF NOT EXISTS aggregator_pages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_username TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    aggregator_type TEXT,
    bio_text        TEXT,
    page_text       TEXT,
    error           TEXT,
    scraped_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(account_username, source_url)
);

CREATE TABLE IF NOT EXISTS detected_links (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    aggregator_page_id  INTEGER NOT NULL,
    url                 TEXT NOT NULL,
    title               TEXT,
    description         TEXT,
    is_subscription     INTEGER DEFAULT 0,
    platform_name       TEXT,
    platform_username   TEXT,
    FOREIGN KEY (aggregator_page_id) REFERENCES aggregator_pages(id)
);

CREATE TABLE IF NOT EXISTS keyword_matches (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    account_username    TEXT NOT NULL,
    keyword             TEXT NOT NULL,
    category            TEXT NOT NULL,
    context             TEXT,
    UNIQUE(account_username, keyword, category)
);

CREATE TABLE IF NOT EXISTS confidence_scores (
    account_username    TEXT PRIMARY KEY,
    score               INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'unlikely',
    subscription_platforms TEXT,
    subscription_urls   TEXT,
    adult_keywords      TEXT,
    last_computed_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_followed_bio_link ON followed_accounts(bio_link);
CREATE INDEX IF NOT EXISTS idx_confidence_score ON confidence_scores(score DESC);
CREATE INDEX IF NOT EXISTS idx_confidence_status ON confidence_scores(status);
"""


# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------

class Database:
    """Thin wrapper around a SQLite connection with pipeline-specific helpers."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle -----------------------------------------------------------

    def connect(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        logger.debug("Database connected: {}", self.db_path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        assert self._conn is not None, "Database not connected"
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    @property
    def conn(self) -> sqlite3.Connection:
        assert self._conn is not None, "Database not connected"
        return self._conn

    # -- agencies ------------------------------------------------------------

    def upsert_agency(
        self,
        agency_name: str,
        instagram_handle: str,
        country: str = "",
        notes: str = "",
    ) -> None:
        self.conn.execute(
            """INSERT INTO agencies (agency_name, instagram_handle, country, notes)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(instagram_handle) DO UPDATE SET
                 agency_name = excluded.agency_name,
                 country = excluded.country,
                 notes = excluded.notes""",
            (agency_name, instagram_handle.lower().strip("@"), country, notes),
        )
        self.conn.commit()

    def get_agencies(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM agencies ORDER BY agency_name"
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_agency_scraped(self, handle: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE agencies SET last_scraped_at = ? WHERE instagram_handle = ?",
            (now, handle.lower()),
        )
        self.conn.commit()

    # -- followed accounts ---------------------------------------------------

    def upsert_followed_account(self, data: dict[str, Any]) -> None:
        username = data["username"].lower()
        self.conn.execute(
            """INSERT INTO followed_accounts
                 (username, display_name, follower_count, bio_text, bio_link,
                  profile_pic_url, is_verified, is_business,
                  discovered_via_agency, last_checked_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(username) DO UPDATE SET
                 display_name = COALESCE(excluded.display_name, display_name),
                 follower_count = COALESCE(excluded.follower_count, follower_count),
                 bio_text = COALESCE(excluded.bio_text, bio_text),
                 bio_link = COALESCE(excluded.bio_link, bio_link),
                 profile_pic_url = COALESCE(excluded.profile_pic_url, profile_pic_url),
                 is_verified = excluded.is_verified,
                 is_business = excluded.is_business,
                 last_checked_at = datetime('now')""",
            (
                username,
                data.get("display_name"),
                data.get("follower_count"),
                data.get("bio_text"),
                data.get("bio_link"),
                data.get("profile_pic_url"),
                int(data.get("is_verified", False)),
                int(data.get("is_business", False)),
                data.get("discovered_via_agency"),
            ),
        )
        self.conn.commit()

    def link_agency_follow(self, agency_handle: str, account_username: str) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO agency_follows (agency_handle, account_username)
               VALUES (?, ?)""",
            (agency_handle.lower(), account_username.lower()),
        )
        self.conn.commit()

    def get_accounts_needing_scrape(self) -> list[dict[str, Any]]:
        """Accounts with a bio_link that haven't been scraped yet."""
        rows = self.conn.execute(
            """SELECT fa.* FROM followed_accounts fa
               WHERE fa.bio_link IS NOT NULL AND fa.bio_link != ''
                 AND fa.username NOT IN (
                   SELECT account_username FROM aggregator_pages
                 )
               ORDER BY fa.username"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_accounts(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM followed_accounts ORDER BY username"
        ).fetchall()
        return [dict(r) for r in rows]

    def is_account_known(self, username: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM followed_accounts WHERE username = ?",
            (username.lower(),),
        ).fetchone()
        return row is not None

    # -- aggregator pages ----------------------------------------------------

    def insert_aggregator_page(
        self,
        account_username: str,
        source_url: str,
        aggregator_type: str,
        bio_text: str = "",
        page_text: str = "",
        error: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO aggregator_pages
                 (account_username, source_url, aggregator_type, bio_text, page_text, error)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(account_username, source_url) DO UPDATE SET
                 aggregator_type = excluded.aggregator_type,
                 bio_text = excluded.bio_text,
                 page_text = excluded.page_text,
                 error = excluded.error,
                 scraped_at = datetime('now')""",
            (account_username.lower(), source_url, aggregator_type, bio_text, page_text, error),
        )
        self.conn.commit()
        return cur.lastrowid or 0

    # -- detected links ------------------------------------------------------

    def insert_detected_link(
        self,
        aggregator_page_id: int,
        url: str,
        title: str = "",
        description: str = "",
        is_subscription: bool = False,
        platform_name: str = "",
        platform_username: str = "",
    ) -> None:
        self.conn.execute(
            """INSERT INTO detected_links
                 (aggregator_page_id, url, title, description,
                  is_subscription, platform_name, platform_username)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                aggregator_page_id, url, title, description,
                int(is_subscription), platform_name, platform_username,
            ),
        )
        self.conn.commit()

    # -- keyword matches -----------------------------------------------------

    def insert_keyword_match(
        self,
        account_username: str,
        keyword: str,
        category: str,
        context: str = "",
    ) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO keyword_matches
                 (account_username, keyword, category, context)
               VALUES (?, ?, ?, ?)""",
            (account_username.lower(), keyword, category, context),
        )
        self.conn.commit()

    # -- confidence scores ---------------------------------------------------

    def upsert_confidence(
        self,
        account_username: str,
        score: int,
        status: str,
        subscription_platforms: str = "",
        subscription_urls: str = "",
        adult_keywords: str = "",
    ) -> None:
        self.conn.execute(
            """INSERT INTO confidence_scores
                 (account_username, score, status,
                  subscription_platforms, subscription_urls, adult_keywords,
                  last_computed_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(account_username) DO UPDATE SET
                 score = excluded.score,
                 status = excluded.status,
                 subscription_platforms = excluded.subscription_platforms,
                 subscription_urls = excluded.subscription_urls,
                 adult_keywords = excluded.adult_keywords,
                 last_computed_at = datetime('now')""",
            (account_username.lower(), score, status,
             subscription_platforms, subscription_urls, adult_keywords),
        )
        self.conn.commit()

    # -- export query --------------------------------------------------------

    def export_rows(self, *, min_score: int = 0) -> list[dict[str, Any]]:
        """Join everything into a flat export-ready structure."""
        rows = self.conn.execute(
            """SELECT
                 fa.username AS instagram_handle,
                 fa.display_name,
                 fa.follower_count,
                 fa.bio_link,
                 ap.aggregator_type,
                 cs.subscription_platforms AS subscription_platforms_found,
                 cs.subscription_urls,
                 cs.adult_keywords AS adult_keywords_matched,
                 cs.score AS confidence_score,
                 cs.status,
                 fa.discovered_via_agency,
                 fa.last_checked_at
               FROM followed_accounts fa
               LEFT JOIN confidence_scores cs ON cs.account_username = fa.username
               LEFT JOIN aggregator_pages ap ON ap.account_username = fa.username
               WHERE COALESCE(cs.score, 0) >= ?
               ORDER BY cs.score DESC, fa.username""",
            (min_score,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- maintenance ---------------------------------------------------------

    def purge_stale(self, retention_days: int) -> int:
        """Delete entries older than *retention_days* that are not flagged."""
        if retention_days <= 0:
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        cur = self.conn.execute(
            """DELETE FROM followed_accounts
               WHERE last_checked_at < ?
                 AND username NOT IN (
                   SELECT account_username FROM confidence_scores
                   WHERE status IN ('confirmed', 'likely_paid_creator')
                 )""",
            (cutoff,),
        )
        self.conn.commit()
        deleted = cur.rowcount
        if deleted:
            logger.info("Purged {} stale accounts (older than {} days)", deleted, retention_days)
        return deleted

    def stats(self) -> dict[str, int]:
        """Quick summary counts."""
        result: dict[str, int] = {}
        for table in ("agencies", "followed_accounts", "aggregator_pages",
                       "detected_links", "keyword_matches", "confidence_scores"):
            row = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
            result[table] = row[0] if row else 0
        return result
