"""Step 1 (network, run on your own machine): fetch every raw input into a local cache.

stats.nba.com blocks datacenter IPs, so this cannot run in a cloud/CI box.
It is resumable: anything already in the cache is skipped, so if it stops
(network blip, rate limit, laptop sleep) just run it again.

    python pipeline/gather.py --smoke   # ~3 min: league endpoints for one team + 2 games, schema check
    python pipeline/gather.py           # full pass (~1.5-3 h, mostly the ~1,230 per-game requests)
    python pipeline/gather.py --status  # what is cached / what failed
"""

import argparse
import importlib
import inspect
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbagm import plan  # noqa: E402
from nbagm.config import RAW_CACHE_PATH, SEASON  # noqa: E402
from nbagm.frames import SchemaError, check_columns, tables  # noqa: E402
from nbagm.rawstore import RawStore  # noqa: E402

BASE_DELAY_S = 0.8
RETRY_DELAYS_S = (5, 15, 45, 120)
TIMEOUT_S = 60


def endpoint_class(module_name):
    module = importlib.import_module(f"nba_api.stats.endpoints.{module_name}")
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if obj.__module__ == module.__name__ and hasattr(obj, "endpoint"):
            return obj
    raise RuntimeError(f"no endpoint class in nba_api.stats.endpoints.{module_name}")


def fetch(req):
    cls = endpoint_class(req.endpoint)
    last_error = None
    for attempt, retry_delay in enumerate((0,) + RETRY_DELAYS_S):
        if retry_delay:
            print(f"    retry {attempt} in {retry_delay}s ({last_error})", flush=True)
            time.sleep(retry_delay)
        try:
            ep = cls(**req.params, timeout=TIMEOUT_S)
            return ep.get_dict()
        except Exception as e:  # network errors, timeouts, JSON decode on throttled responses
            last_error = f"{type(e).__name__}: {e}"
    raise RuntimeError(last_error)


def run(store, requests, label, check_schema=False):
    todo = [r for r in requests if not store.has(r.endpoint, r.params)]
    print(f"[{label}] {len(requests)} requests, {len(requests) - len(todo)} cached, "
          f"{len(todo)} to fetch", flush=True)
    failed = 0
    for i, req in enumerate(todo, 1):
        print(f"  ({i}/{len(todo)}) {req.name}", flush=True)
        try:
            payload = fetch(req)
            if check_schema:
                check_columns(req.name, req.endpoint, payload)
            store.put(req.endpoint, req.params, payload)
        except SchemaError as e:
            print(f"  SCHEMA MISMATCH: {e}", flush=True)
            store.record_failure(req.endpoint, req.params, e)
            failed += 1
        except Exception as e:
            print(f"  FAILED after retries: {e}", flush=True)
            store.record_failure(req.endpoint, req.params, e)
            failed += 1
        time.sleep(BASE_DELAY_S + random.uniform(0, 0.6))
    return failed


def regular_season_game_ids(store):
    req = plan.by_name(plan.league_requests())[f"team_game_log_{SEASON}"]
    df = tables(req.endpoint, store.get(req.endpoint, req.params))["LeagueGameLog"]
    return sorted(df["GAME_ID"].astype(str).unique())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--smoke", action="store_true",
                    help="fetch a small subset and verify every column the build needs exists")
    ap.add_argument("--status", action="store_true", help="report cache contents and failures")
    ap.add_argument("--cache", default=str(RAW_CACHE_PATH))
    args = ap.parse_args()

    store = RawStore(args.cache)
    league = plan.league_requests()

    if args.status:
        teams = [r for t in plan.TEAM_IDS for r in plan.team_requests(t)]
        print(f"league: {sum(store.has(r.endpoint, r.params) for r in league)}/{len(league)}")
        print(f"team:   {sum(store.has(r.endpoint, r.params) for r in teams)}/{len(teams)}")
        try:
            games = regular_season_game_ids(store)
            reqs = [r for g in games for r in plan.game_requests(g)]
            print(f"game:   {sum(store.has(r.endpoint, r.params) for r in reqs)}/{len(reqs)} "
                  f"({len(games)} games)")
        except KeyError:
            print("game:   (team game log not fetched yet)")
        for endpoint, params, error in store.failures():
            print(f"FAILED {endpoint} {params}: {error}")
        return 0

    if args.smoke:
        team = plan.TEAM_IDS[0]
        failed = run(store, league + plan.team_requests(team), "smoke: league + 1 team",
                     check_schema=True)
        games = regular_season_game_ids(store)[:2]
        failed += run(store, [r for g in games for r in plan.game_requests(g)],
                      "smoke: 2 games", check_schema=True)
        print("\nSMOKE OK - run without --smoke for the full pass." if failed == 0 else
              f"\nSMOKE FOUND {failed} PROBLEM(S) - send me the output above before the full run.")
        return 1 if failed else 0

    failed = run(store, league, "league", check_schema=True)
    failed += run(store, [r for t in plan.TEAM_IDS for r in plan.team_requests(t)], "teams",
                  check_schema=True)
    games = regular_season_game_ids(store)
    failed += run(store, [r for g in games for r in plan.game_requests(g)],
                  f"games ({len(games)})", check_schema=True)
    if failed:
        print(f"\n{failed} request(s) failed. Re-run this script to retry just those.")
        return 1
    print(f"\nAll raw inputs cached in {args.cache}.\nNext: python pipeline/build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
