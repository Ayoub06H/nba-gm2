
# Tendency Derivation Methodology

## Same hard rule as attributes and traits

No reputation, name recognition, media narrative, or subjective "feel" for how a player plays factors into a derived tendency value, ever. A tendency is a pure function of how often a player's real play-by-play behavior shows him choosing something, out of the real opportunities he had to choose it.

## The pipeline: Beta-Binomial only, every stat a proportion with an explicit denominator

Tendencies store directly as a 0–1 value with no percentile conversion or curve reshaping (unlike attributes — see `02-attribute-derivation-formulas.md`). Because the stored value itself must already be a bounded proportion, **every tendency below is defined as an explicit count of events ÷ an explicit count of real opportunities**, and shrunk with the same **Beta-Binomial empirical-Bayes method** attributes use (S1 in doc 02: prior fit via method-of-moments on the real league-wide distribution of that specific proportion). No tendency in this doc is expressed as "per 100 possessions" or any other unbounded rate — if a stat can't be phrased as a true proportion, it doesn't belong in this doc as written (see "Parked" below).

**Build guard (applies to every proportion in this doc and every S1 input in doc 02 and doc 04):** before shrinkage the build asserts `numerator ≤ denominator` for every player and every statistic. If any player violates it, the build aborts and prints the statistic and the offending players. Nothing is clipped, capped or dropped to make it pass: a violation means the definition is wrong and must be fixed in the doc.

**Either/or pair tendencies** (Catch-and-Shoot vs. Pull-Up, Box-Out vs. Leak-Out, Drive-and-Kick vs. Drive-to-Finish, Pass-First vs. Score-First) are one slider: the real stat is the share between the two named options specifically (A ÷ (A + B)).

**Relationship to attributes.** Under the reuse rule in doc 02, the same real statistic can appear in a tendency and in an attribute (for example, attempts per 100 inside a shooting rating, and the attempt share here). A tendency says how often he chooses it; the attribute says how well, and for some skills also how much. Phase 3 checks whether tendency and attribute together over-credit high-volume players.

## Shot profile

| Tendency | Numerator | Denominator (real opportunity count) |
|---|---|---|
| Three-Point Attempt Rate | 3PA | FGA |
| Mid-Range Attempt Rate | Mid-range attempts (`SHOT_ZONE_BASIC` = "Mid-Range") | FGA |
| Rim Attempt Rate | Attempts with `SHOT_DISTANCE` < 6 ft (matches the "Less Than 6Ft" category in doc 02) | FGA |
| Catch-and-Shoot vs. Pull-Up (either/or) | Pull-up jumper attempts | Catch-and-shoot + pull-up jumper attempts (LeagueDashPlayerPtShot `GeneralRange` "Catch and Shoot" and "Pullups") |
| Shot Clock Usage | FGA taken with 7 or fewer seconds left on the shot clock (LeagueDashPlayerPtShot with `ShotClockRange`, or play-by-play shot-clock field if the parameter is unavailable; `--smoke` decides) | Total FGA (a single direct rate — not a share against only the earliest bucket, so no real data is discarded) |

## On-ball creation / usage

| Tendency | Numerator | Denominator |
|---|---|---|
| Isolation Frequency | Isolation possessions (Synergy play-type, a directly-published frequency) | Total offensive possessions used |
| Post-Up Frequency | Post-up possessions (same dashboard) | Total offensive possessions used |
| Pick-and-Roll Usage (as ball-handler) | Ball-handler PnR possessions (same dashboard) | Total offensive possessions used |
| Drive-and-Kick vs. Drive-to-Finish (either/or) | Passes thrown off a tracked drive (`DRIVE_PASSES`) | `DRIVE_PASSES` + `DRIVE_FGA` (both published columns on the Drives dashboard) |
| Pass-First vs. Score-First / Shot-Hunting (either/or) | `PASSES_MADE` | `PASSES_MADE` + `FGA`. **Corrected (G23):** a touch can contain several passes, so `PASSES_MADE ÷ TOUCHES` exceeded 1 for some players (for example 1,409 passes on 1,210 touches) and is not a proportion. The share of his pass-or-shoot decisions that are passes is bounded by construction |
| Foul/Contact-Seeking | FTA | FGA + FTA. **Corrected:** the earlier FTA ÷ FGA is not a proportion (a player can have more FTA than FGA) and so cannot take a Beta-Binomial shrinkage; FTA ÷ (FGA + FTA) is the share of his shooting events that end at the line |

## Off-ball movement

| Tendency | Numerator | Denominator |
|---|---|---|
| Cutting Frequency | Cut possessions (Synergy play-type) | Total offensive possessions used |
| Screen-Setting Willingness | Screen Assists (official Hustle Stats) | Team offensive possessions played while this player was on the floor |

## Defensive approach

| Tendency | Numerator | Denominator |
|---|---|---|
| Gamble-for-Steals Frequency | Deflections (official Hustle Stats — the NBA's own definition already encompasses both successful-steal and non-steal deflections, so using Deflections alone avoids double-counting Steals, which the Steals attribute measures as a success rate) | Defensive possessions played |
| Defensive Foul Aggression | Personal fouls committed | Defensive possessions played |

## Hustle / effort

| Tendency | Numerator | Denominator |
|---|---|---|
| Offensive Rebound Crash Rate | `OREB_CHANCES` (Rebounding tracking dashboard, not Hustle Stats) | Team missed FGA while this player was on the floor |
| Defensive Rebound Box-Out vs. Leak-Out | `DEF_BOXOUTS` (official Hustle Stats) | Team defensive-rebound situations while this player was on the floor (opponent missed FGA plus missed final FTs while on court); "leak-out" is the implicit complement (1 − this rate), not an independently measured count |
| Fast Break Leak-Out | Transition possessions (Synergy play-type) | Total offensive possessions used |
| Loose Ball / Floor Dive Willingness | `LOOSE_BALLS_RECOVERED` (official Hustle Stats) | Total possessions (offensive + defensive) played |
| Charge-Taking Willingness | `CHARGES_DRAWN` (official Hustle Stats) | Defensive possessions played |

## Data gettability

All numerators and denominators come from the same sources as doc 02's checklist (Synergy play types, LeagueDashPlayerPtShot, Drives/Possessions/Rebounding in LeagueDashPtStats, Hustle Stats, ShotChartDetail, and play-by-play for possessions and fouls). Where a column is only "smoke"-verified there, it is the same here: a missing column aborts the build with the name of the tendency affected, and no tendency is silently approximated.

## Parked — not computed in Phase 1, for a specific real reason

Four tendencies from the original draft list are **cut from Phase 1**, not faked with an invented proxy. Each hits the same kind of wall already acknowledged elsewhere in this design (the possession-engine doc's "one hard limit": full defender-contest geometry is proprietary data that was never made public). Parking these is the honest move rather than forcing a formula onto data that doesn't exist:

- **Closeout Aggressiveness** — the original definition needed closest-defender-distance data *from the defender's own perspective* (how tight was his specific closeout), but the public closest-defender-distance tracking only exists from the *shooter's* side. The real signal that does exist here — opponent efficiency on shots he contests — already lives inside the On-Ball Defense **attribute**, so this doesn't disappear from the design.
- **Help Defense Aggressiveness** — the only public source for help-capacity attempts (`HELP_FGA` in LeagueSeasonMatchups) was confirmed to be 0 in every one of 151,960 real rows. The one proxy, `(CONTESTED_SHOTS − D_FGA) ÷ CONTESTED_SHOTS`, goes negative for some players because the two counts use different contest definitions, so it is not a proportion. Parked, not clipped. If a future source (or a check showing no player is negative) removes the problem, it comes back with that numerator and denominator. The signal that does exist lives in the Off-Ball Defense attribute (contests beyond closest-defender volume).
- **Screen Navigation: Over vs. Under** — requires knowing, per ball-screen event, whether the defender fought over or went under. Public play-by-play doesn't record ball-screen events at that level of detail at all, so there's no real sequence to measure this from.
- **Switch Willingness** — requires tracking which specific defender was assigned to the ball-handler immediately before and after each screen. The public Matchup dashboard only publishes season-aggregate matchup totals, not possession-level assignment changes.

If a future data source changes this (e.g. licensed Second Spectrum access), these four can be added back using the same methodology as everything else here.

## Sources
- stats.nba.com public tracking dashboards: Play Type (Synergy-powered), Catch and Shoot / Pull Up, Drives, Touches, Shot Clock, Rebounding, Matchup
- NBA official Hustle Stats: Screen Assists, Deflections, Loose Balls Recovered, Charges Drawn, Box Outs
