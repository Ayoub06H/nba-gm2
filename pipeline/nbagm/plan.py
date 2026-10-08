"""Every stats.nba.com request the pipeline makes, defined once.

gather.py fetches exactly these; build.py looks the same requests up in the raw
cache by name, so the two can never disagree about parameters.

Some requests feed attributes/traits that are currently blocked on a
documentation gap (see GAPS.md). They are gathered anyway so that resolving a
gap only means re-running the offline build, not another network pass.
"""

from dataclasses import dataclass

from .config import COMBINE_FIRST_YEAR, COMBINE_LAST_YEAR, DURABILITY_SEASONS, SEASON, SEASON_TYPE

TEAM_IDS = (
    1610612737, 1610612738, 1610612739, 1610612740, 1610612741, 1610612742,
    1610612743, 1610612744, 1610612745, 1610612746, 1610612747, 1610612748,
    1610612749, 1610612750, 1610612751, 1610612752, 1610612753, 1610612754,
    1610612755, 1610612756, 1610612757, 1610612758, 1610612759, 1610612760,
    1610612761, 1610612762, 1610612763, 1610612764, 1610612765, 1610612766,
)

GENERAL_RANGES = ("", "Catch and Shoot", "Pullups", "Less Than 10 ft")
CLOSE_DEF_DIST_RANGES = (
    "", "0-2 Feet - Very Tight", "2-4 Feet - Tight", "4-6 Feet - Open", "6+ Feet - Wide Open",
)
SHOT_DIST_RANGES = ("", ">=10.0")
SHOT_CLOCK_RANGES = (
    "24-22", "22-18 Very Early", "18-15 Early", "15-7 Average", "7-4 Late", "4-0 Very Late",
    "ShotClock Off",
)
PT_MEASURE_TYPES = (
    "SpeedDistance", "Rebounding", "Possessions", "CatchShoot", "PullUpShot", "Defense",
    "Drives", "Passing", "ElbowTouch", "PostTouch", "PaintTouch", "Efficiency",
)
PLAY_TYPES = (
    "Isolation", "Transition", "PRBallHandler", "PRRollman", "Postup", "Spotup", "Handoff",
    "Cut", "OffScreen", "OffRebound", "Misc",
)
DEFENSE_CATEGORIES = (
    "Overall", "3 Pointers", "2 Pointers", "Less Than 6Ft", "Less Than 10Ft", "Greater Than 15Ft",
)


@dataclass(frozen=True)
class Request:
    name: str
    endpoint: str      # module name in nba_api.stats.endpoints
    params: dict

    def __hash__(self):
        return hash((self.name, self.endpoint, tuple(sorted(self.params.items()))))


def _req(name, endpoint, **params):
    return Request(name, endpoint, params)


def league_requests():
    """Season-level requests (no per-game fan-out)."""
    s, rs = SEASON, SEASON_TYPE
    out = [
        _req("player_index", "playerindex", season=s, league_id="00"),
        _req("player_base_totals", "leaguedashplayerstats", season=s,
             season_type_all_star=rs, measure_type_detailed_defense="Base",
             per_mode_detailed="Totals"),
        _req("player_advanced_totals", "leaguedashplayerstats", season=s,
             season_type_all_star=rs, measure_type_detailed_defense="Advanced",
             per_mode_detailed="Totals"),
        _req("player_shot_locations", "leaguedashplayershotlocations", season=s,
             season_type_all_star=rs, distance_range="By Zone", per_mode_detailed="Totals",
             measure_type_simple="Base"),
        _req("player_hustle", "leaguehustlestatsplayer", season=s,
             season_type_all_star=rs, per_mode_time="Totals"),
        _req("player_clutch_base", "leaguedashplayerclutch", season=s,
             season_type_all_star=rs, measure_type_detailed_defense="Base",
             per_mode_detailed="Totals"),
        _req("player_clutch_advanced", "leaguedashplayerclutch", season=s,
             season_type_all_star=rs, measure_type_detailed_defense="Advanced",
             per_mode_detailed="Totals"),
        _req("team_base_totals", "leaguedashteamstats", season=s, season_type_all_star=rs,
             measure_type_detailed_defense="Base", per_mode_detailed="Totals"),
        _req("team_advanced_totals", "leaguedashteamstats", season=s, season_type_all_star=rs,
             measure_type_detailed_defense="Advanced", per_mode_detailed="Totals"),
    ]
    for period in (1, 2, 3, 4):
        out.append(_req(f"player_base_totals_q{period}", "leaguedashplayerstats", season=s,
                        season_type_all_star=rs, measure_type_detailed_defense="Base",
                        per_mode_detailed="Totals", period=period))
    for g in GENERAL_RANGES:
        for d in CLOSE_DEF_DIST_RANGES:
            for sd in SHOT_DIST_RANGES:
                out.append(_req(pt_shot_name(g, d, sd), "leaguedashplayerptshot", season=s,
                                season_type_all_star=rs, per_mode_simple="Totals",
                                general_range_nullable=g, close_def_dist_range_nullable=d,
                                shot_dist_range_nullable=sd))
    for sc in SHOT_CLOCK_RANGES:
        out.append(_req(shot_clock_name(sc), "leaguedashplayerptshot", season=s,
                        season_type_all_star=rs, per_mode_simple="Totals",
                        shot_clock_range_nullable=sc))
    for m in PT_MEASURE_TYPES:
        out.append(_req(f"pt_{m}", "leaguedashptstats", season=s, season_type_all_star=rs,
                        per_mode_simple="Totals", player_or_team="Player", pt_measure_type=m))
    for grouping in ("offensive", "defensive"):
        for pt in PLAY_TYPES:
            out.append(_req(play_type_name(grouping, pt), "synergyplaytypes", season=s,
                            season_type_all_star=rs, per_mode_simple="Totals",
                            player_or_team_abbreviation="P", play_type_nullable=pt,
                            type_grouping_nullable=grouping))
    for cat in DEFENSE_CATEGORIES:
        out.append(_req(pt_defend_name(cat), "leaguedashptdefend", season=s,
                        season_type_all_star=rs, per_mode_simple="Totals",
                        defense_category=cat))
    for season in DURABILITY_SEASONS:
        out.append(_req(f"player_game_logs_{season}", "playergamelogs", season_nullable=season,
                        season_type_nullable=rs))
        out.append(_req(f"team_game_log_{season}", "leaguegamelog", season=season,
                        season_type_all_star=rs, player_or_team_abbreviation="T"))
    for year in range(COMBINE_FIRST_YEAR, COMBINE_LAST_YEAR + 1):
        out.append(_req(f"combine_anthro_{year}", "draftcombineplayeranthro",
                        season_year=str(year), league_id="00"))
        out.append(_req(f"combine_drills_{year}", "draftcombinedrillresults",
                        season_year=str(year), league_id="00"))
    return out


def team_requests(team_id):
    s, rs = SEASON, SEASON_TYPE
    return [
        _req(f"roster_{team_id}", "commonteamroster", team_id=team_id, season=s),
        _req(f"matchups_def_{team_id}", "leagueseasonmatchups", season=s,
             season_type_playoffs=rs, per_mode_simple="Totals", def_team_id_nullable=team_id),
        _req(f"shot_chart_{team_id}", "shotchartdetail", team_id=team_id, player_id=0,
             season_nullable=s, season_type_all_star=rs, context_measure_simple="FGA"),
    ]


def game_requests(game_id):
    """Every request for one 2025-26 game. Play-by-play primary source is cdn.nba.com
    liveData (it carries assist/block/steal/foul-drawn ids, doc 11); PlayByPlayV3 is the
    backup. The box-score summary carries the inactive list (Durability, doc 04); V3 is
    used because nba_api flags BoxScoreSummaryV2 data as missing from April 2025 on."""
    return [
        _req(f"pbp_{game_id}", "playbyplayv3", game_id=game_id),
        _req(f"rotation_{game_id}", "gamerotation", game_id=game_id),
        _req(f"box_{game_id}", "boxscoretraditionalv3", game_id=game_id),
        _req(f"live_pbp_{game_id}", "live.playbyplay", game_id=game_id),
        _req(f"summary_{game_id}", "boxscoresummaryv3", game_id=game_id),
    ]


def durability_game_requests(game_id):
    """Earlier seasons of the Durability window only need appearances, DNP comments and
    inactive lists (doc 04)."""
    return [
        _req(f"box_{game_id}", "boxscoretraditionalv3", game_id=game_id),
        _req(f"summary_{game_id}", "boxscoresummaryv3", game_id=game_id),
    ]


def pt_shot_name(general_range, close_def, shot_dist):
    return f"pt_shot|{general_range or 'All'}|{close_def or 'All'}|{shot_dist or 'All'}"


def shot_clock_name(shot_clock_range):
    return f"pt_shot_clock|{shot_clock_range}"


def play_type_name(grouping, play_type):
    return f"synergy|{grouping}|{play_type}"


def pt_defend_name(category):
    return f"pt_defend|{category}"


def by_name(requests):
    return {r.name: r for r in requests}


def all_league_and_team_requests():
    reqs = list(league_requests())
    for t in TEAM_IDS:
        reqs.extend(team_requests(t))
    return reqs
