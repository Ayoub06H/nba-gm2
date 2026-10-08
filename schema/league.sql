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
    player_id          INTEGER PRIMARY KEY,
    team_id            INTEGER NOT NULL REFERENCES teams(team_id),
    first_name         TEXT NOT NULL,
    last_name          TEXT NOT NULL,
    jersey             TEXT,
    position           TEXT NOT NULL,     -- exactly as published: G, F, C, G-F, F-C, C-F, F-G
    position_index     INTEGER NOT NULL,  -- doc 11: G=1, G-F/F-G=2, F=3, F-C/C-F=4, C=5
    birth_date         TEXT,
    experience         TEXT,
    age                REAL,
    height_in          REAL,
    weight_lb          REAL,
    wingspan_in        REAL,
    wingspan_imputed   INTEGER NOT NULL DEFAULT 0,  -- 1 = regression-imputed (doc 11)
    games_played       INTEGER NOT NULL DEFAULT 0,  -- with this team, 2025-26 regular season
    games_started      INTEGER NOT NULL DEFAULT 0,  -- with this team
    minutes_per_game   REAL NOT NULL DEFAULT 0,     -- with this team
    depth_rank         INTEGER NOT NULL,            -- 1..5 = inferred starters; then by minutes per game
    no_data            INTEGER NOT NULL DEFAULT 0,  -- 1 = no on-floor exposure in 2025-26 (doc 02)
    placeholder_rating INTEGER NOT NULL DEFAULT 0   -- 1 = every rated attribute is the placeholder 40.0
);

-- Doc 02: rating = 99 x mid-rank league percentile of the attribute's Score (unrounded).
-- score/percentile are NULL for placeholder ratings.
CREATE TABLE player_attributes (
    player_id   INTEGER NOT NULL REFERENCES players(player_id),
    attribute   TEXT NOT NULL,
    score       REAL,
    percentile  REAL,
    rating      REAL NOT NULL,
    placeholder INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, attribute)
);

-- Doc 03: Beta-Binomial-shrunk real rate stored directly in [0,1].
CREATE TABLE player_tendencies (
    player_id   INTEGER NOT NULL REFERENCES players(player_id),
    tendency    TEXT NOT NULL,
    numerator   REAL,
    denominator REAL,
    raw_rate    REAL,
    value       REAL NOT NULL,
    PRIMARY KEY (player_id, tendency)
);

-- Doc 04. tier is -2..2 (0 = no trait).
CREATE TABLE player_traits (
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    trait     TEXT NOT NULL,
    value     REAL,        -- the trait's underlying shrunk value (NULL without exposure)
    z_score   REAL NOT NULL,
    tier      INTEGER NOT NULL,
    tier_name TEXT,        -- NULL for tier 0 (no trait)
    PRIMARY KEY (player_id, trait)
);

-- Contract stub per doc 11: nullable, filled only from a named real source.
CREATE TABLE contracts (
    player_id       INTEGER PRIMARY KEY REFERENCES players(player_id),
    salary          REAL,
    years_remaining INTEGER
);

CREATE TABLE derivation_status (
    kind    TEXT NOT NULL,     -- attribute | tendency | trait | measurable | player_field
    name    TEXT NOT NULL,
    status  TEXT NOT NULL,     -- derived
    note    TEXT,
    PRIMARY KEY (kind, name)
);

-- Audit trail: every fitted prior, every component, every model parameter.
CREATE TABLE priors (
    kind      TEXT NOT NULL,
    name      TEXT NOT NULL,
    family    TEXT NOT NULL,   -- beta | gamma | normal | gamma_rr | scaled_inv_chi2
    param1    REAL,            -- alpha | k | tau^2 | k | nu0 (NULL = infinite: point mass)
    param2    REAL,            -- beta  | m | -     | -  | s0^2
    mean      REAL,
    n_players INTEGER NOT NULL,
    PRIMARY KEY (kind, name)
);

CREATE TABLE components (
    player_id INTEGER NOT NULL,
    field     TEXT NOT NULL,
    component TEXT NOT NULL,
    value     REAL,
    z         REAL,
    PRIMARY KEY (player_id, field, component)
);

CREATE TABLE blend_weights (
    field     TEXT NOT NULL,
    component TEXT NOT NULL,
    weight    REAL NOT NULL,
    PRIMARY KEY (field, component)
);

CREATE TABLE model_parameters (
    model TEXT NOT NULL,
    key   TEXT NOT NULL,
    value REAL,
    PRIMARY KEY (model, key)
);

CREATE TABLE build_notes (
    field TEXT NOT NULL,
    note  TEXT NOT NULL
);

CREATE TABLE data_checks (
    name   TEXT PRIMARY KEY,
    ok     INTEGER NOT NULL,
    detail TEXT
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
