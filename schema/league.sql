-- League database schema (Phase 1).
--
-- Single source of truth for the SQLite file the C# game reads at runtime.
-- Written by pipeline/build.py, read by src/NbaGm.Core (LeagueLoader).
-- Values are derived results only, never the raw API dump.

PRAGMA foreign_keys = ON;

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE teams (
    team_id      INTEGER PRIMARY KEY,
    abbreviation TEXT NOT NULL,
    city         TEXT NOT NULL,
    name         TEXT NOT NULL
);

-- One row per player on a final 2025-26 roster.
CREATE TABLE players (
    player_id         INTEGER PRIMARY KEY,
    team_id           INTEGER NOT NULL REFERENCES teams(team_id),
    first_name        TEXT NOT NULL,
    last_name         TEXT NOT NULL,
    jersey            TEXT,
    listed_position   TEXT,            -- as published by stats.nba.com (G, F, C, G-F, F-C, ...)
    position          TEXT,            -- PG/SG/SF/PF/C per doc 11; NULL until its source is specified
    birth_date        TEXT,
    experience        TEXT,
    height_in         REAL,
    weight_lb         REAL,
    wingspan_in       REAL,
    wingspan_imputed  INTEGER NOT NULL DEFAULT 0,  -- 1 = regression-imputed (doc 11)
    games_played      INTEGER NOT NULL DEFAULT 0,  -- with this team, 2025-26 regular season
    games_started     INTEGER NOT NULL DEFAULT 0,  -- with this team
    minutes_per_game  REAL NOT NULL DEFAULT 0,     -- with this team
    depth_rank        INTEGER NOT NULL             -- 1..5 = inferred starters; then by minutes per game
);

-- Attribute pipeline stages per doc 02. rating is the final 0-99 value
-- (unrounded double); it stays NULL until every stage before it is derivable.
CREATE TABLE player_attributes (
    player_id     INTEGER NOT NULL REFERENCES players(player_id),
    attribute     TEXT NOT NULL,
    successes     REAL,        -- real count (or points, for Gamma-Poisson stats)
    opportunities REAL,        -- real opportunity count / exposure
    raw_value     REAL,        -- successes / opportunities, unshrunk
    shrunk_value  REAL,        -- empirical-Bayes posterior mean
    percentile    REAL,        -- league percentile in (0,1), oriented so higher = better
    rating        REAL,        -- final 0-99
    PRIMARY KEY (player_id, attribute)
);

-- Tendencies per doc 03: Beta-Binomial-shrunk real rate stored directly in [0,1].
CREATE TABLE player_tendencies (
    player_id   INTEGER NOT NULL REFERENCES players(player_id),
    tendency    TEXT NOT NULL,
    numerator   REAL,
    denominator REAL,
    raw_rate    REAL,
    value       REAL,
    PRIMARY KEY (player_id, tendency)
);

-- Traits per doc 04. tier is -2..2 (0 = no trait).
CREATE TABLE player_traits (
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    trait     TEXT NOT NULL,
    value     REAL,        -- the trait's underlying real value
    z_score   REAL,        -- SDs from the reference (league, or the runs-test null for Streaky)
    tier      INTEGER,
    tier_name TEXT,        -- NULL for tier 0 (no trait)
    PRIMARY KEY (player_id, trait)
);

-- Contract stub per doc 11 (per-season salary, years remaining).
CREATE TABLE contracts (
    player_id       INTEGER PRIMARY KEY REFERENCES players(player_id),
    salary          REAL NOT NULL,
    years_remaining INTEGER NOT NULL
);

-- Which fields are derived and which are blocked on a documentation gap.
CREATE TABLE derivation_status (
    kind    TEXT NOT NULL,     -- attribute | tendency | trait | measurable | player_field
    name    TEXT NOT NULL,
    status  TEXT NOT NULL,     -- derived | partial | blocked
    gap_ids TEXT,              -- comma-separated ids from pipeline/GAPS.md
    note    TEXT,
    PRIMARY KEY (kind, name)
);

-- Fitted empirical-Bayes priors, kept for audit.
CREATE TABLE priors (
    kind      TEXT NOT NULL,
    name      TEXT NOT NULL,
    family    TEXT NOT NULL,   -- beta | gamma | none
    param1    REAL,            -- alpha | k
    param2    REAL,            -- beta  | prior mean (theta, see shrinkage.py)
    mean      REAL,
    n_players INTEGER NOT NULL,
    PRIMARY KEY (kind, name)
);

-- Real 2025-26 regular-season schedule and results (Phase 3 input).
CREATE TABLE games (
    game_id       TEXT PRIMARY KEY,
    game_date     TEXT NOT NULL,
    home_team_id  INTEGER NOT NULL REFERENCES teams(team_id),
    away_team_id  INTEGER NOT NULL REFERENCES teams(team_id),
    home_points   INTEGER,
    away_points   INTEGER
);

-- Real team season totals (Phase 3 validation layer, doc 11).
CREATE TABLE team_season_stats (
    team_id INTEGER NOT NULL REFERENCES teams(team_id),
    stat    TEXT NOT NULL,
    value   REAL,
    PRIMARY KEY (team_id, stat)
);
