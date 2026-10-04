"""Offline checks on the gather plan: every request must construct against nba_api."""

import gather
from nbagm import plan


def all_requests():
    reqs = plan.all_league_and_team_requests()
    reqs += plan.game_requests("0022500001")
    return reqs


def test_every_request_constructs_with_valid_parameter_names():
    for req in all_requests():
        cls = gather.endpoint_class(req.endpoint)
        cls(**req.params, get_request=False)   # TypeError on an unknown parameter


def test_request_names_are_unique():
    names = [r.name for r in all_requests()]
    assert len(names) == len(set(names))


def test_thirty_teams():
    assert len(set(plan.TEAM_IDS)) == 30
