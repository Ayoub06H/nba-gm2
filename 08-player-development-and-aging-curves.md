
# Player Development & Progression

## Core model: same baseline-plus-modifier pattern as everything else

A player's year-over-year attribute movement is not hand-tuned and not a free random walk. It's three layers stacked, same shape as tendencies-vs-coaching-system and traits-vs-SD-distance elsewhere in this design:

1. **Baseline** — a real, data-derived aging curve from the player's own statistical comps (reusing the comp-query mechanism already decided for prospect generation, not a new bucketing system)
2. **Context modifier** — a systematic push up or down based on real usage/role (minutes, role assignment from the tactics system) versus what his comps got at the same career stage
3. **Variance** — a smaller, genuine random roll every season

Most seasons track close to the baseline curve, exactly as expected for an "average" player following an average path. Context and variance are real but second-order most of the time — they only produce an outlier career when they stack in the same direction for multiple seasons.

## The baseline: a real, bias-corrected aging curve from statistical comps

A naive "average stats by age" chart is wrong in a specific, well-documented way: survivorship bias. The average 33-year-old still in the league is good — the mediocre ones already got cut — so a straight cross-sectional age chart understates how much decline any individual actually experiences. The real, named fix for this (the **Delta Method**, originally from baseball aging-curve research, adapted for basketball) tracks the *same players'* year-over-year change and only counts seasons where a player actually played meaningful minutes in both year N and N+1, rather than averaging whoever happened to be in the league at each age.

This curve is built once per comp cohort — the same statistical-comp set already used to generate a prospect's floor/ceiling band — not a separate archetype taxonomy. One mechanism doing two jobs.

**Critical constraint: the curve applies to hidden attributes, not box-score stats.** This engine's entire premise is that stats emerge from attributes run through the possession engine — never a tuning target. So the baseline curve is derived from real advanced stats (the observable signal) but expresses itself as movement in the underlying attribute values; the box-score improvement a player shows each season is what falls out downstream of that, same as everywhere else in this design.

## Context modifier: real usage against the role-assignment system

Rather than inventing a new "usage" number, this plugs directly into the tactics system already built: a player who receives meaningfully more or fewer real reps in his role (per the Layer 1 coach/role-assignment system) than his comp cohort typically got at the same career stage gets pushed above or below his baseline curve accordingly. A prospect buried on the bench behind a bad depth chart, or thrust into a role in a great-fit system with heavy run, both get a real, causal (not hidden-dice) deviation from the guideline curve.

## Variance: a smaller, genuine random layer

On top of baseline + context, every season gets a real random roll — smaller in weight than the context modifier most of the time, but present every year, which is what keeps any two careers with identical comps and identical usage from looking mechanically identical.

## Breakout and bust are the same mechanism, not special cases

No separate "breakout roll" exists. A player in an unusually good situation (strong context modifier) who also runs a bit hot on variance for several consecutive seasons can have his cumulative trajectory climb out the top of the comp band he started in — a real breakout with a real cause. The mirror case is just as real: sustained poor context plus unlucky variance can push a player below the floor of his own band entirely, not just short of his ceiling — a genuine bust, same math. Both directions are symmetric and explained by the same stack of baseline + context + variance, consistent with how mismatch amplification elsewhere in this design lets extreme inputs produce extreme (not averaged-away) outcomes.

## Hidden makeup traits — parked, not designed

Work-ethic/coachability-type factors (already explicitly cut from the visible trait system for having no real statistical shadow) were proposed as a hidden multiplier on development rate here, since a development-rate modifier doesn't need the visible-trait system's tier-naming/stat-proxy requirement. Explicitly deferred for now at the user's call — not rejected, just not part of the current design. First place to revisit if development ends up feeling too mechanically deterministic once built.

## Implementation: where the real data actually lives

This does **not** mean shipping a live connection to an NBA API, and it does not mean bundling the entire contents of any API. Two reasons: this is a single-player, offline-capable game, and the mechanic only needs a specific, bounded slice of data — historical player-season (or game-level, if the Delta Method needs finer granularity to correctly pair consecutive seasons) box scores and advanced stats, for comp-matching and curve-fitting. It doesn't need schedules, news, injury reports, or anything else a live sports API also serves.

The right shape is an **offline data pipeline, run once (or periodically refreshed) during development, not at runtime**:
1. Pull historical player-season stats from a real source.
2. Compute the derived artifacts the game actually needs offline: comp-match feature vectors per player-season, and the Delta-Method aging-curve table per comp cohort.
3. Bake the *results* — not the raw API dump — into a local dataset shipped with the game (a SQLite file or similar), which the game queries locally at runtime with no network dependency.

## Data source: resolved, not still open

**`stats.nba.com`, via the `nba_api` Python package, is the primary and required source — not a choice among equals.** This follows directly from what the rest of this design actually needs, not a separate preference: `02-attribute-derivation-formulas.md` and `03-tendency-derivation-formulas.md` both depend heavily on stats.nba.com's tracking-level dashboards (shot zones, closest-defender distance, play-type frequency, Touches, Drives, Shot Clock, official Hustle Stats) that simply don't exist in `balldontlie.io`'s simpler box-score/schedule API. Since Phase 1 needs those exact dashboards for attributes and tendencies regardless, the development engine's historical-comp pipeline uses the same source rather than introducing a second one for no reason.

**`balldontlie.io` and a static historical dataset (e.g. a Kaggle NBA dump) remain real, used supplements, not competing primary choices** — specifically for whatever stats.nba.com's tracking-era coverage doesn't reach: older-era seasons (tracking data effectively starts around 2013-14) for deep historical comps, and anything stats.nba.com doesn't publish at all (real injury/games-missed history for the Durability trait, real draft-combine measurements for wingspan imputation).

This already matches the "run locally, not from the cloud build environment" architecture decision in `11-phase-1-3-build-and-data-pipeline-plan.md` (stats.nba.com is known to block datacenter/cloud IPs) — one data-gathering pass, run once on your own machine, covers attributes, tendencies, traits, and the development engine's historical comps together, producing one committed local dataset with no further network dependency.

**Redistribution caveat, as before:** stats.nba.com's endpoints are unofficial/undocumented and Basketball-Reference-sourced bulk dumps have terms restricting redistribution — fine for a personal/non-commercial project as this currently is, worth revisiting only if this is ever distributed or sold.

## Still open
- Exact comp-cohort sizing/similarity threshold for the aging-curve bucketing (how many comps count, how similar they need to be) — a Phase 3+/development-engine calibration question, not a Phase 1 blocker, since Phase 1 loads a single-season snapshot and doesn't run aging/development at all
- Numeric magnitude of the variance layer relative to the context modifier — not yet quantified, best refined once there's a validation harness to compare simulated career-outcome distributions against real ones — same non-blocking status as above
