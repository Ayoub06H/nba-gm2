# Phase 1 data pipeline

Two steps, run on your own machine (stats.nba.com blocks cloud and datacenter IPs):

| Step | Script | Network | Output |
|---|---|---|---|
| 1. Gather | `gather.py` | yes, stats.nba.com via `nba_api` | `data/raw/raw_cache_2025_26.sqlite`: verbatim API responses (git-ignored) |
| 2. Build | `build.py` | none | `data/league_2025_26.sqlite`: derived values only; commit this file |

The build reads only the raw cache, so you can re-run it as often as needed, for example after a
doc change, without fetching anything again.

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

`build.py` prints a summary: lineup-reconstruction quality, the doc 02 data checks (defender
dashboard consistency, play-by-play to shot-chart join, DNP comments), the turnover types seen, the
fitted wingspan regression and notes such as Rule A components that got weight 0.

If any field cannot be derived exactly as the docs define it (for example a numerator larger than
its denominator for some player), the build lists every such field with the offending players,
writes the list to `data/raw/build_report.txt`, and stops **without** writing the league file.
Send me that list. (`--allow-incomplete` writes the file anyway, with the failures marked, for
inspection only.)

On success, commit `data/league_2025_26.sqlite` and send me the summary.

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
- **Defender dashboards:** all categories.
- **Clutch splits.**
- **Per shot:** the full shot chart.
- **Per game:** play-by-play (cdn.nba.com liveData, with PlayByPlayV3 as backup), rotations, box
  score and the box-score summary (inactive list).
- **Durability window:** box scores and inactive lists for every game of 2023-24 to 2025-26, plus
  team and player game logs.
- **Draft combine:** anthropometrics and drills, 2000-2025.

The full list of requests lives in `nbagm/plan.py`.

## Layout

```
gather.py            step 1 (network)
build.py             step 2 (offline)
GAPS.md              open questions on the docs and the mechanical readings the build makes
nbagm/plan.py        every request, defined once
nbagm/frames.py      raw payload -> DataFrame, plus the required-column checks
nbagm/pbp.py         lineups, stints and per-player events from play-by-play (liveData or V3)
nbagm/league.py      assembles real per-player counts, shots, stints, contests, game logs
nbagm/shrinkage.py   S1-S4 and the Scaled-Inv-chi2 prior (docs 02, 04)
nbagm/models.py      E1 shot models, stint ridge (RAPM family), E3 Poisson, Rule A, imputation
nbagm/common.py      population, percentile / Z / rating, shrinkage context and audit trail
nbagm/attributes.py  the 27 rated attributes (doc 02)
nbagm/tendencies.py  the 20 tendencies (doc 03)
nbagm/traits.py      the 5 traits (doc 04)
nbagm/measurables.py wingspan imputation and depth chart (doc 11)
tests/               unit tests + a full build on a synthetic league in the real response shapes
```

Run the tests with `cd pipeline && python -m pytest`.
