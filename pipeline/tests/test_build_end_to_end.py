"""Full offline build against a synthetic raw cache (no network)."""

import sqlite3

import pytest

import build
from nbagm import derive
from tests.synthetic import PLAYERS_PER_TEAM, write_store


@pytest.fixture(scope="module")
def league_db(tmp_path_factory):
    d = tmp_path_factory.mktemp("league")
    write_store(d / "raw.sqlite")
    out = d / "league.sqlite"
    build.build(d / "raw.sqlite", out)
    con = sqlite3.connect(str(out))
    yield con
    con.close()


def scalar(con, sql):
    return con.execute(sql).fetchone()[0]


def test_every_rostered_player_on_thirty_teams(league_db):
    assert scalar(league_db, "SELECT COUNT(DISTINCT team_id) FROM players") == 30
    assert scalar(league_db, "SELECT COUNT(*) FROM players") == 30 * PLAYERS_PER_TEAM


def test_every_player_has_a_row_for_every_field(league_db):
    n = scalar(league_db, "SELECT COUNT(*) FROM players")
    assert scalar(league_db, "SELECT COUNT(*) FROM player_attributes") == n * len(derive.ATTRIBUTES)
    assert scalar(league_db, "SELECT COUNT(*) FROM player_tendencies") == n * len(derive.TENDENCIES)
    assert scalar(league_db, "SELECT COUNT(*) FROM player_traits") == n * len(derive.TRAITS)


def test_tendencies_are_complete_and_bounded(league_db):
    assert scalar(league_db, "SELECT COUNT(*) FROM player_tendencies t JOIN derivation_status d "
                             "ON d.kind = 'tendency' AND d.name = t.tendency "
                             "WHERE d.status = 'derived' AND t.value IS NULL") == 0
    assert scalar(league_db, "SELECT COUNT(*) FROM player_tendencies WHERE value < 0 OR value > 1") == 0


def test_non_proportion_is_reported_not_patched(league_db):
    # The synthetic league has players with FTA > FGA (gap F1): Foul/Contact-Seeking
    # must come out NULL and marked failed, never clipped into [0, 1].
    status, note = league_db.execute(
        "SELECT status, note FROM derivation_status WHERE name = 'foul_contact_seeking'").fetchone()
    assert status == "failed" and "successes > opportunities" in note
    assert scalar(league_db, "SELECT COUNT(*) FROM player_tendencies "
                             "WHERE tendency = 'foul_contact_seeking' AND value IS NOT NULL") == 0


def test_player_who_never_played_gets_the_prior_mean(league_db):
    rows = league_db.execute(
        "SELECT t.value, p.mean FROM player_tendencies t JOIN players pl USING (player_id) "
        "JOIN priors p ON p.kind = 'tendency' AND p.name = t.tendency "
        "WHERE pl.games_played = 0").fetchall()
    assert rows and all(v == pytest.approx(m) for v, m in rows)


def test_attribute_stages(league_db):
    partial = {a.key for a in derive.ATTRIBUTES if a.stage == "percentile"}
    for key, n_pct, n_rating in league_db.execute(
            "SELECT attribute, SUM(percentile IS NOT NULL), SUM(rating IS NOT NULL) "
            "FROM player_attributes GROUP BY attribute"):
        assert n_rating == 0                     # G1 blocks every final rating
        assert (n_pct > 0) == (key in partial)
    assert scalar(league_db, "SELECT COUNT(*) FROM player_attributes "
                             "WHERE percentile <= 0 OR percentile >= 1") == 0


def test_starters_and_wingspans(league_db):
    assert scalar(league_db, "SELECT COUNT(*) FROM players WHERE depth_rank <= 5") == 150
    assert scalar(league_db, "SELECT COUNT(*) FROM players WHERE wingspan_in IS NULL") == 0
    assert scalar(league_db, "SELECT COUNT(*) FROM players WHERE wingspan_imputed = 1") > 0


def test_games_and_status_tables(league_db):
    assert scalar(league_db, "SELECT COUNT(*) FROM games") == 30
    blocked = {r[0] for r in league_db.execute(
        "SELECT name FROM derivation_status WHERE status = 'blocked'")}
    assert {"durability", "consistency", "clutch", "position", "contract"} <= blocked


def test_reconstructed_lineups_match_box_score_minutes(league_db):
    # Most synthetic games have no rotation response, like the real API.
    err = float(scalar(league_db, "SELECT value FROM meta WHERE key = 'lineup_minutes_mean_abs_error'"))
    assert err < 0.01
    assert scalar(league_db, "SELECT value FROM meta WHERE key = 'pbp_events_unresolved'") == "0"
