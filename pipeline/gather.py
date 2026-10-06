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

BASE_DELAY_S = 1.5          # pause between requests (plus up to 1 s of jitter)
MAX_DELAY_S = 6.0
RETRY_DELAYS_S = (5, 20)    # quick retries for a one-off network blip
TIMEOUT_S = 60

# stats.nba.com throttles clients that ask too fast: it answers with empty
# bodies (JSONDecodeError) or times out, for every request, for a while.
# Several failures in a row means that, so pause instead of burning retries,
# then continue more slowly.
THROTTLE_AFTER_FAILURES = 3
COOLDOWN_S = 600
MAX_COOLDOWNS_WITHOUT_SUCCESS = 4


class Throttled(RuntimeError):
    pass


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


class Pacer:
    """Spacing between requests, slowed down after every throttling episode."""

    def __init__(self):
        self.delay = BASE_DELAY_S
        self.consecutive_failures = 0
        self.cooldowns_without_success = 0

    def success(self):
        self.consecutive_failures = 0
        self.cooldowns_without_success = 0

    def failure(self):
        self.consecutive_failures += 1
        if self.consecutive_failures < THROTTLE_AFTER_FAILURES:
            return
        self.cooldowns_without_success += 1
        if self.cooldowns_without_success > MAX_COOLDOWNS_WITHOUT_SUCCESS:
            raise Throttled(
                "stats.nba.com is still refusing requests after "
                f"{MAX_COOLDOWNS_WITHOUT_SUCCESS} cool-downs. Stop here and run this script "
                "again in a few hours (everything fetched so far is kept).")
        self.delay = min(self.delay * 1.5, MAX_DELAY_S)
        resume = time.strftime("%H:%M", time.localtime(time.time() + COOLDOWN_S))
        print(f"  {self.consecutive_failures} failures in a row: stats.nba.com is throttling. "
              f"Pausing {COOLDOWN_S // 60} min (until ~{resume}), then continuing at one "
              f"request per ~{self.delay:.1f}s. No need to do anything.", flush=True)
        time.sleep(COOLDOWN_S)
        self.consecutive_failures = 0

    def wait(self):
        time.sleep(self.delay + random.uniform(0, 1.0))


def run(store, requests, label, check_schema=False, pacer=None):
    pacer = pacer or Pacer()
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
            pacer.success()
        except SchemaError as e:
            print(f"  SCHEMA MISMATCH: {e}", flush=True)
            store.record_failure(req.endpoint, req.params, e)
            failed += 1
            pacer.success()   # the server answered; this is not throttling
        except Exception as e:
            print(f"  FAILED: {e}", flush=True)
            store.record_failure(req.endpoint, req.params, e)
            failed += 1
            pacer.failure()
        pacer.wait()
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

    pacer = Pacer()
    try:
        everything = league + [r for t in plan.TEAM_IDS for r in plan.team_requests(t)]
        run(store, everything, "league + teams", check_schema=True, pacer=pacer)
        games = regular_season_game_ids(store)
        game_reqs = [r for g in games for r in plan.game_requests(g)]
        run(store, game_reqs, f"games ({len(games)})", check_schema=True, pacer=pacer)
        # One more pass over anything that failed (usually requests caught in a throttle window).
        missing = [r for r in everything + game_reqs if not store.has(r.endpoint, r.params)]
        if missing:
            run(store, missing, "second pass over failed requests", check_schema=True, pacer=pacer)
    except Throttled as e:
        print(f"\n{e}")
        return 1
    missing = [r for r in everything + game_reqs if not store.has(r.endpoint, r.params)]
    if missing:
        print(f"\n{len(missing)} request(s) still missing. Run this script again later to retry "
              "just those; if the same ones keep failing, run --status and send me the output.")
        return 1
    print(f"\nAll raw inputs cached in {args.cache}.\nNext: python pipeline/build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
