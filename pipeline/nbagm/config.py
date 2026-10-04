"""Fixed settings for the Phase 1 data pipeline."""

from pathlib import Path

SEASON = "2025-26"
SEASON_TYPE = "Regular Season"

# Durability uses a trailing 3-season window (doc 04).
DURABILITY_SEASONS = ("2023-24", "2024-25", "2025-26")

# Draft combine years pulled for wingspan and the combine-based physical inputs.
COMBINE_FIRST_YEAR = 2000
COMBINE_LAST_YEAR = 2025

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_CACHE_PATH = DATA_DIR / "raw" / "raw_cache_2025_26.sqlite"
LEAGUE_DB_PATH = DATA_DIR / "league_2025_26.sqlite"
SCHEMA_PATH = REPO_ROOT / "schema" / "league.sql"
