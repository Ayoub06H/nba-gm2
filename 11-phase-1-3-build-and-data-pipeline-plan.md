
# First Build Phase: Implementation Decisions

Supersedes the original "vertical slice" framing. Nothing here is a disposable test — this is the real game, built in an order chosen to catch problems early and cheaply rather than built all at once with no feedback until the end.

## Phase order

**Phase 1 — the entire league, fully loaded, nothing simulated yet:**
All 30 real teams, every real player on every roster, for the 2025-26 season (see season-choice note below). Not a subset of teams or players — loading everyone costs the same pipeline work as loading a few, so there's no reason to artificially narrow it. Each player gets:
- Real Attributes (27 rated), derived exactly per `02-attribute-derivation-formulas.md` — per-attribute real stat mapping, empirical-Bayes shrinkage, difficulty/load adjustment, an efficiency-plus-volume score where both are meaningful, then `rating = 99 × mid-rank percentile`. Nothing here is left for the implementer to invent; if a specific attribute's source stat isn't obvious from that doc, the doc is incomplete and needs fixing before coding around it, not a reason to guess.
- Real Tendencies, derived exactly per `03-tendency-derivation-formulas.md` — real frequency stat, the same empirical-Bayes shrinkage mechanism as attributes, stored directly as the 0-1 rate (no curve reshaping — tendencies are rates, not skills).
- Real Traits, computed per the fully-specified `04-player-trait-system.md` (all five: Durability, Consistency, Clutch, Hustle, Streaky), including its empirical-Bayes variance-shrinkage resolution for thin-sample players.

Players who are rostered but never played get a **placeholder rating of 40 on every rated attribute** plus `no_data` and `placeholder_rating` flags (a temporary, explicit exception described in `02-attribute-derivation-formulas.md`, "Population"; their tendencies take the prior rate and their traits are "no trait"), so every rostered player has every value. Phase 1 is "done" when every real player in the league has real, derived values for all of the above — not partially populated, not a hand-picked sample.

**Phase 2 — the possession engine, full move list, unit-tested before integration:**
Every move from the possession-engine doc gets built, not a reduced subset — a partial move list (e.g. just Drive/Pull-up/Catch-and-shoot/Pass) can't produce anything that resembles real basketball closely enough for a season-level comparison to mean anything; it would just obviously look like simplified basketball, which isn't a useful signal. To keep this debuggable despite the larger scope, **each move's resolution formula is unit-tested in isolation** (known synthetic inputs → expected probability shape) before being wired into the full game loop — the rigor that justified a smaller scope before is preserved through testing discipline instead of a feature cut. The engine's non-linear attribute→probability curve is fit here, per move, against real outcomes.

**Phase 3 — the real checkpoint: simulate the real 2025-26 season.**
Not "one game" and not "a few hundred random games" — the actual real schedule (which real team played which real team, how many times), using the real rosters/attributes from Phase 1 and the full engine from Phase 2. A single simulated game tells you almost nothing (too much variance to separate "working" from "broken"); the real season, compared game-by-game and in aggregate against what actually happened, is the first checkpoint that can actually tell you whether the engine works — not just whether league-average stats land in the right neighborhood, but whether real good teams still come out ahead, whether a real blowout looks like a blowout in the sim, etc.

## Season choice: 2025-26, not 2024-25

As of October 2026, 2025-26 is the most recently **completed** NBA season (ran Oct 2025–June 2026). Used consistently for rosters, player stats, derived attributes/tendencies/traits, the real schedule for Phase 3, and the validation comparison — never mixed with a different season, so Phase 3 always compares the simulation against the same league it was built from.

## The one hard limit this doesn't remove

Full defender-contest tracking (exactly how much space a defender conceded on a given shot) is proprietary NBA/Second Spectrum data that was never publicly available. Shooting formulas can be real-data-fit from public shot-chart data; anything needing live contest quality still starts from a reasoned structure — a data-availability ceiling, not something more data-gathering fixes.

## Wingspan imputation for missing players

Public wingspan only exists for draft-combine attendees. For players missing it: impute from a regression fit **on the real combine data itself** (wingspan ≈ a + b×height, fit from players who have both measurements) — not an assumed universal ratio. Filling a real gap from a relationship derived from real data, same category of move as the Delta Method or comp-query system elsewhere in this design.

## Depth charts and rotation order

No public endpoint publishes real depth charts. Starters are inferred from real games-started; rotation order/minutes from real minutes-per-game — both real, tracked stats.

## Data gathering: run locally, not from the cloud build environment

**Draft-combine measurements come from nba_api `DraftCombineStats` (anthropometrics and athletic tests). Durability uses box-score and inactive-list game logs for 2023-24 to 2025-26 (see `04-player-trait-system.md`).**

**Primary source: `stats.nba.com`, via the `nba_api` Python package.** This is a decision, not a placeholder — `02-attribute-derivation-formulas.md` and `03-tendency-derivation-formulas.md` both depend on its tracking-level dashboards (shot zones, closest-defender distance and contest counts, play-type frequency, Touches, Drives, Shot Clock, official Hustle Stats, clutch splits), none of which exist in simpler free APIs. `balldontlie.io` and a static historical dataset (e.g. a Kaggle dump) remain real supplements for what stats.nba.com doesn't cover: real injury/games-missed history (Durability trait) and real draft-combine measurements (wingspan imputation, the Lateral Quickness/Vertical fallback inputs).

The cloud build environment's network policy blocks the needed NBA data sources, and `stats.nba.com` specifically is known to block datacenter/cloud IPs regardless of policy. **Play-by-play comes from `cdn.nba.com`'s liveData play-by-play JSON (it carries assist, block, steal and foul-drawn player ids), with nba_api `PlayByPlayV3` and the `shufinskiy/nba_data` archive as backups; `PlayByPlayV2` is dead in nba_api 1.11.4 and V3 has no assister ids.**

**The entire data-gathering step runs once as a script on your own machine**, producing one committed SQLite file (covering the full league, the real 2025-26 schedule/game log for Phase 3, and everything attributes/tendencies/traits need). Everything downstream builds against that committed file with no network dependency.

## Resolved ambiguities carried over from the original scoping pass

- **Internal attribute storage:** unrounded `double` on the 0-99 display range, rounded only for display — equivalent in precision to a separate 0-999 internal scale, one fewer conversion to maintain.
- **Tendency scale:** `double` from 0 to 1, stored directly as the shrunk real rate per `03-tendency-derivation-formulas.md` — no curve reshaping. Either/or pairs (Catch-and-Shoot vs. Pull-Up, Over vs. Under, Box-Out vs. Leak-Out) are one slider, computed as the real share between the two options.
- **Effective reach:** estimated from Height and Wingspan (inches), Weight in pounds.
- **Contests:** folded directly into shot resolution for now (matched-up defender's On-Ball Defense, Rim Protection, and reach feed the formula directly) — a tracked simplification against the possession doc's full "Contest a shot" move, to revisit, not a dropped requirement.
- **Matchups:** every Player gets a Position stored **exactly as the NBA publishes it** (CommonPlayerInfo / CommonTeamRoster): the 2025-26 rosters use seven labels (G, F, C, G-F, F-C, C-F, F-G); none is inferred or hand-assigned. Where an ordering is needed, the label's index along the guard-to-center axis is G=1, G-F=2, F=3, F-C=4, C=5, with a pair counted the same in either order (F-G = 2, C-F = 4). Defenders match to the attacker with the closest index by default, ties broken by the smaller height difference (a real measurement).
- **Mismatch amplification:** keep the reach term multiplicative, per the possession doc's worked example. The full mismatch cross-check (validating specific extreme-asymmetry cases, not just aggregate averages) is still owed — explicitly tracked, not forgotten.
- **Contract:** per-season salary and years remaining are **nullable**. Phase 1 fills them only if a real source is named and reachable; otherwise they stay empty, and nothing in Phases 1–3 reads them. No salary is estimated or invented.

## Validation approach — 2025-26 NBA regular season

Primary check is Phase 3 (the real season replay) described above. League-average aggregate figures (pace, points, FG%, 3P%, FT%, shot-attempt mix, turnovers, rebounds, assists) for 2025-26 should be pulled from the same real data source as everything else, not hand-typed from memory, and used as one layer of the comparison alongside the game-by-game/team-by-team checks Phase 3 enables. Phase 3 is also where the efficiency/volume split inside attribute ratings is checked for over-crediting high-volume players.

## Sources
- [Basketball-Reference NBA season league averages](https://www.basketball-reference.com/leagues/)
- `02-attribute-derivation-formulas.md`, `03-tendency-derivation-formulas.md`, `04-player-trait-system.md` — the full real-data specs Phase 1 implements against
