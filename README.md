# Cleaner.io Creator Discovery Pipeline

B2B lead generation tool that discovers OnlyFans/adult content creators by scraping agency Instagram accounts, following the chain: **Agency IG → followed accounts → bio link → aggregator page → subscription platform detection**.

Built for [Cleaner.io](https://cleaner.io), a DMCA takedown service that helps creators remove leaked content.

## How It Works

The pipeline runs 7 stages:

1. **Agency Ingestion** — Reads a CSV of agency Instagram handles
2. **Instagram Scraper** — Fetches each agency's following list (Instaloader/Apify/instagrapi)
3. **Bio Link Extraction** — Identifies aggregator links (Linktree, Beacons, etc.) in bios
4. **Aggregator Scraping** — Fetches aggregator pages, extracts all outbound links
5. **Platform Detection** — Matches links against OnlyFans, Fansly, ManyVids, and 11 other platforms
6. **Keyword Detection** — Scans text for adult content indicators with confidence scoring
7. **Export** — Generates CRM-ready CSVs sorted by confidence score

## Setup

### Requirements

- Python 3.11+
- Instagram credentials (for following-list access)
- Optional: residential proxies, Apify API key, Playwright

### Install

```bash
# Clone and install
git clone <repo-url> && cd chatters
pip install -e ".[dev]"

# For JS-heavy aggregators (Stan.store, Beacons)
pip install -e ".[playwright]"
playwright install chromium

# Copy and configure environment
cp .env.example .env
# Edit .env with your credentials
```

### Configuration (.env)

```bash
# Instagram auth (required for Stage 2)
IG_USERNAME=your_ig_username
IG_PASSWORD=your_ig_password

# Optional: multiple sessions for rotation
IG_SESSIONS=user1:pass1,user2:pass2

# Optional: Apify (alternative IG provider)
APIFY_API_KEY=your_key

# Optional: residential proxies
PROXY_URLS=http://user:pass@proxy1:port,http://user:pass@proxy2:port

# Rate limiting (seconds between requests)
REQUEST_DELAY_MIN=2.0
REQUEST_DELAY_MAX=7.0
```

## Usage

### Full pipeline run

```bash
python -m pipeline run --agencies sample_agencies.csv
```

### Test with a single agency

```bash
python -m pipeline run --agencies sample_agencies.csv --single-agency unrulyagency
```

### Dry run (no actual scraping)

```bash
python -m pipeline run --agencies sample_agencies.csv --dry-run
```

### Skip Instagram scraping (process existing data)

```bash
python -m pipeline run --agencies sample_agencies.csv --skip-ig
```

### Choose IG provider

```bash
python -m pipeline run --agencies sample_agencies.csv --provider apify
python -m pipeline run --agencies sample_agencies.csv --provider instagrapi
```

### Export results only

```bash
python -m pipeline export
```

### View database stats

```bash
python -m pipeline stats
```

## Output

The pipeline generates three CSVs in the `output/` directory:

| File | Contents |
|------|----------|
| `all_creators.csv` | Every discovered account with confidence scores |
| `confirmed_creators.csv` | Only confirmed creators (score >= 80) ready for outreach |
| `review_queue.csv` | Borderline accounts (score 40-60) needing manual review |

### Confidence Scoring

| Score | Meaning |
|-------|---------|
| 100 | Confirmed subscription platform link found |
| 80-95 | Multiple adult content keywords detected |
| 65-79 | Platform-adjacent indicators (e.g. "OF" reference) |
| 50-64 | Soft keywords + emoji indicators |
| 30-49 | Single soft keyword — needs manual review |
| 0-29 | Unlikely to be a paid creator |

### Detected Platforms

OnlyFans, Fansly, ManyVids, Fanvue, FanCentro, JustForFans, MYM, LoyalFans, Scrile Connect, AdmireMe, iFans, Friends2Follow, Frisk, SextPanther

### Detected Aggregators

Linktree, Beacons, AllMyLinks, Stan.store, Snipfeed, Carrd, Bio.fm, Linkin.bio, Linkpop, Hoo.be, Komi, Direct.me, Withkoji, Campsite, Tap.bio, Lnk.bio, Shorby, Solo.to, Flowpage

## Project Structure

```
pipeline/
  __init__.py
  __main__.py              # python -m pipeline entry point
  main.py                  # CLI (Click) and pipeline orchestration
  config.py                # .env loading and Config dataclass
  database.py              # SQLite schema, CRUD, and maintenance
  instagram_scraper.py     # Stage 2: pluggable IG providers
  aggregator_scraper.py    # Stages 3+4: aggregator detection + scraping
  subscription_detector.py # Stage 5: platform URL matching
  keyword_detector.py      # Stage 6: keyword scanning + confidence scoring
  exporter.py              # Stage 7: CSV generation
  tests/
    test_keyword_detector.py
    test_subscription_detector.py
    test_aggregator_detector.py
```

## Running Tests

```bash
python -m pytest pipeline/tests/ -v
```

## Anti-Detection Measures

- Realistic user-agent rotation (Chrome, Firefox, Safari on multiple OSes)
- Randomised delays between requests (2-7 seconds, configurable)
- Residential proxy rotation support (Bright Data, Smartproxy, Oxylabs)
- Multiple Instagram session rotation
- Automatic backoff on HTTP 429/401/403 with exponential retry
- Caching in SQLite to avoid re-scraping known accounts

## Legal and Ethical Considerations

- **Public data only** — Only scrapes publicly available profiles and pages. Private Instagram accounts are skipped.
- **Rate limiting** — Respects platform rate limits even when not enforced. Default 2-7 second delays between requests.
- **No content storage** — Never downloads or stores actual photos/videos. Only stores metadata and public profile information.
- **Data retention** — Auto-purges entries older than 90 days (configurable) unless flagged for active outreach.
- **Deduplication** — Accounts discovered via multiple agencies are merged, not duplicated.
- **Manual review** — Borderline confidence scores (40-60) are flagged for human review before outreach.
- **Intended use** — This tool is designed for B2B lead generation to help creators protect their content through DMCA takedown services. It should not be used for harassment, stalking, or any purpose that violates platform terms of service.

## Agency CSV Format

```csv
agency_name,instagram_handle,country,notes
Unruly Agency,unrulyagency,US,Major talent management agency
```

Required columns: `agency_name`, `instagram_handle`. Optional: `country`, `notes`.
