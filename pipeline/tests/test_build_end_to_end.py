"""Full offline build against a synthetic raw cache (no network)."""

import sqlite3

import pytest

import build
from nbagm import plan
from nbagm.attributes import ATTRIBUTES, PLACEHOLDER_RATING
from nbagm.rawstore import RawStore
from nbagm.tendencies import TENDENCIES
from nbagm.traits import TRAITS
from tests.synthetic import PLAYERS_PER_TEAM, V3_ONLY_GAMES, write_store


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


def test_every_player_has_every_value(league_db):
    n = scalar(league_db, "SELECT COUNT(*) FROM players")
    assert scalar(league_db, "SELECT COUNT(*) FROM player_attributes WHERE rating IS NOT NULL") \
        == n * len(ATTRIBUTES) == n * 27
    assert scalar(league_db, "SELECT COUNT(*) FROM player_tendencies WHERE value IS NOT NULL") \
        == n * len(TENDENCIES) == n * 20
    assert scalar(league_db, "SELECT COUNT(*) FROM player_traits WHERE tier IS NOT NULL") \
        == n * len(TRAITS) == n * 5
    assert scalar(league_db, "SELECT value FROM meta WHERE key = 'complete'") == "1"
    assert scalar(league_db, "SELECT COUNT(*) FROM derivation_status WHERE status != 'derived' "
                             "AND kind IN ('attribute', 'tendency', 'trait')") == 0


def test_ratings_are_99_times_mid_rank_percentile(league_db):
    n_pop = scalar(league_db, "SELECT COUNT(*) FROM players WHERE no_data = 0")
    lo, hi = league_db.execute("SELECT MIN(rating), MAX(rating) FROM player_attributes "
                               "WHERE placeholder = 0 AND attribute = 'free_throw'").fetchone()
    assert lo == pytest.approx(99 * 0.5 / n_pop) and hi == pytest.approx(99 * (n_pop - 0.5) / n_pop)
    assert scalar(league_db, "SELECT COUNT(*) FROM player_attributes "
                             "WHERE placeholder = 0 AND ABS(rating - 99 * percentile) > 1e-9") == 0


def test_players_without_exposure_get_the_placeholder_and_flags(league_db):
    rows = league_db.execute("SELECT player_id, no_data, placeholder_rating FROM players "
                             "WHERE games_played = 0").fetchall()
    assert rows and all(nd == 1 and pr == 1 for _, nd, pr in rows)
    assert scalar(league_db, "SELECT COUNT(*) FROM player_attributes a JOIN players p USING (player_id) "
                             f"WHERE p.no_data = 1 AND (a.rating != {PLACEHOLDER_RATING} OR a.placeholder != 1)") == 0
    assert scalar(league_db, "SELECT COUNT(*) FROM player_attributes a JOIN players p USING (player_id) "
                             "WHERE p.no_data = 0 AND a.placeholder != 0") == 0
    # tendencies take the prior rate; traits are "no trait"
    for value, mean in league_db.execute(
            "SELECT t.value, pr.mean FROM player_tendencies t JOIN players p USING (player_id) "
            "JOIN priors pr ON pr.kind = 'tendency' AND pr.name = t.tendency WHERE p.no_data = 1"):
        assert value == pytest.approx(mean)
    assert scalar(league_db, "SELECT COUNT(*) FROM player_traits t JOIN players p USING (player_id) "
                             "WHERE p.no_data = 1 AND (t.tier != 0 OR t.z_score != 0)") == 0


def test_tendencies_are_bounded_rates(league_db):
    assert scalar(league_db, "SELECT COUNT(*) FROM player_tendencies WHERE value <= 0 OR value >= 1") == 0


def test_trait_tiers_follow_z(league_db):
    for z, t, name in league_db.execute("SELECT z_score, tier, tier_name FROM player_traits"):
        expected = 2 if z >= 2 else 1 if z >= 1 else -2 if z <= -2 else -1 if z <= -1 else 0
        assert t == expected and ((name is None) == (t == 0))


def test_positions_are_published_labels_with_doc_11_index(league_db):
    index = {"G": 1, "G-F": 2, "F-G": 2, "F": 3, "F-C": 4, "C-F": 4, "C": 5}
    for pos, idx in league_db.execute("SELECT position, position_index FROM players"):
        assert index[pos] == idx


def test_audit_tables_are_filled(league_db):
    assert scalar(league_db, "SELECT COUNT(*) FROM priors") > 50
    assert scalar(league_db, "SELECT COUNT(DISTINCT field) FROM components") >= 27
    w = dict(league_db.execute("SELECT field, SUM(weight) FROM blend_weights GROUP BY field").fetchall())
    assert w["offensive_iq"] == pytest.approx(1) and w["defensive_iq"] == pytest.approx(1)
    assert scalar(league_db, "SELECT COUNT(*) FROM data_checks WHERE ok = 0") == 0
    lam = [v for (v,) in league_db.execute("SELECT value FROM model_parameters WHERE key = 'lambda'")]
    assert lam and all(10 - 1e-9 <= v <= 1e5 + 1e-6 for v in lam)


def test_play_by_play_sources(league_db):
    assert scalar(league_db, "SELECT value FROM meta WHERE key = 'pbp_games_v3'") == str(V3_ONLY_GAMES)
    err = float(scalar(league_db, "SELECT value FROM meta WHERE key = 'lineup_minutes_mean_abs_error'"))
    assert err < 0.01
    assert scalar(league_db, "SELECT value FROM meta WHERE key = 'pbp_events_unresolved'") == "0"


def test_starters_wingspans_weights(league_db):
    assert scalar(league_db, "SELECT COUNT(*) FROM players WHERE depth_rank <= 5") == 150
    assert scalar(league_db, "SELECT COUNT(*) FROM players WHERE wingspan_in IS NULL") == 0
    assert scalar(league_db, "SELECT COUNT(*) FROM players WHERE wingspan_imputed = 1") > 0
    assert scalar(league_db, "SELECT COUNT(*) FROM players WHERE weight_lb IS NULL") == 0


def test_home_and_away_come_from_the_box_score(league_db):
    home, away = league_db.execute(
        "SELECT home_team_id, away_team_id FROM games ORDER BY game_date, game_id LIMIT 1").fetchone()
    assert home != away


def test_proportion_violation_stops_the_build_and_names_the_offender(tmp_path):
    raw = tmp_path / "raw.sqlite"
    write_store(raw, seed=1)
    store = RawStore(raw)
    req = plan.by_name(plan.all_league_and_team_requests())["pt_Rebounding"]
    payload = store.get(req.endpoint, req.params)
    rows = payload["resultSets"][0]["rowSet"]
    headers = payload["resultSets"][0]["headers"]
    victim = rows[0][0]
    rows[0][headers.index("OREB_CHANCES")] = 10_000      # more chances than team misses on floor
    store.put(req.endpoint, req.params, payload)
    store.close()
    out = tmp_path / "league.sqlite"
    with pytest.raises(build.BuildFailed):
        build.build(raw, out)
    assert not out.exists()
    report = (tmp_path / "build_report.txt").read_text()
    assert "offensive_rebound_crash_rate" in report and str(victim) in report
