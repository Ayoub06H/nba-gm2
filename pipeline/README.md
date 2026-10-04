# Phase 1 data pipeline

Two steps, run on your own machine (stats.nba.com blocks cloud and datacenter IPs):

| Step | Script | Network | Output |
|---|---|---|---|
| 1. Gather | `gather.py` | yes, stats.nba.com via `nba_api` | `data/raw/raw_cache_2025_26.sqlite`: verbatim API responses (git-ignored) |
| 2. Build | `build.py` | none | `data/league_2025_26.sqlite`: derived values only; commit this file |

The build reads only the raw cache, so you can re-run it as often as needed, for example after a
gap in `GAPS.md` is resolved, without fetching anything again.

## Setup (once)

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r pipeline/requirements.txt
```

## Run

From the repo root:

```bash
python pipeline/gather.py --smoke   # ~3-5 min: league dashboards, 1 team, 2 games + column check
```

The smoke run checks every column the build reads against the live responses. If it prints
`SMOKE FOUND n PROBLEM(S)`, send me that output before the full run; a renamed upstream column is
much cheaper to fix now than after two hours of fetching.

```bash
python pipeline/gather.py           # full pass, ~1.5-3 h (about 3,700 per-game requests)
python pipeline/gather.py --status  # progress / failures at any time
```

The full pass is resumable: anything already cached is skipped, so if it stops (rate limit, sleep,
network), run the same command again. Failed requests are retried with backoff and listed by
`--status`.

```bash
python pipeline/build.py            # a few minutes; writes data/league_2025_26.sqlite
dotnet run --project tools/NbaGm.Phase1Check   # Phase 1 definition-of-done check
```

`build.py` prints a summary: lineup-reconstruction quality, the fitted wingspan regression, any
field whose real data broke the method's assumptions, and every field still blocked on a doc gap.
Commit `data/league_2025_26.sqlite` and send me that summary.

## What gets pulled (2025-26 regular season)

- **Rosters:** all 30 teams.
- **Box scores:** totals and per-quarter splits.
- **Shot zones:** shot locations.
- **Shot tracking:** closest-defender × catch-and-shoot/pull-up × distance grids, and shot-clock
  buckets.
- **Tracking dashboards (12):** Catch & Shoot, Pull Up, Drives, Passing, Touches, Rebounding, Speed
  & Distance, Defense, and others.
- **Play types:** Synergy, all 11, offense and defense.
- **Hustle stats.**
- **Matchups:** season matchups.
- **Defender dashboards:** all categories.
- **Clutch splits.**
- **Per shot:** the full shot chart.
- **Per game:** play-by-play, rotations and box score.
- **Durability window:** team and player game logs for 2023-24 to 2025-26.
- **Draft combine:** anthropometrics and drills, 2000-2025.

The full list of requests lives in `nbagm/plan.py`. Some inputs feed fields that are blocked today.
They're pulled now so that resolving those gaps needs no second network run.

## Layout

```
gather.py            step 1 (network)
build.py             step 2 (offline)
GAPS.md              documentation gaps blocking specific fields, with proposed resolutions
nbagm/plan.py        every request, defined once
nbagm/frames.py      raw payload -> DataFrame, plus the required-column checks
nbagm/pbp.py         on-floor accounting from play-by-play + rotations
nbagm/league.py      assembles real per-player counts
nbagm/shrinkage.py   Beta-Binomial, Gamma-Poisson, Scaled-Inv-chi2 (doc 02)
nbagm/derive.py      every attribute / tendency / trait formula (docs 02-04)
tests/               unit tests + a full build on a synthetic league in the real response shapes
```

Run the tests with `cd pipeline && python -m pytest`.
