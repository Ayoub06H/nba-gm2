
# Tendency Derivation Methodology

## Same hard rule as attributes and traits

No reputation, name recognition, media narrative, or subjective "feel" for how a player plays factors into a derived tendency value, ever. A tendency is a pure function of how often a player's real play-by-play behavior shows him choosing something, out of the real opportunities he had to choose it.

## The pipeline: Beta-Binomial only, every stat a proportion with an explicit denominator

Tendencies store directly as a 0–1 value with no percentile conversion or curve reshaping (unlike attributes — see `02-attribute-derivation-formulas.md`). Because the stored value itself must already be a bounded proportion, **every tendency below is defined as an explicit count of events ÷ an explicit count of real opportunities**, and shrunk with the same **Beta-Binomial empirical-Bayes method** attributes use (prior fit via method-of-moments on the real league-wide distribution of that specific proportion). No tendency in this doc is expressed as "per 100 possessions" or any other unbounded rate — if a stat can't be phrased as a true proportion, it doesn't belong in this doc as written (see "Parked" section below for the ones that couldn't).

**Either/or pair tendencies** (Catch-and-Shoot vs. Pull-Up, Box-Out vs. Leak-Out) are one slider: the real stat is the share between the two named options specifically (A ÷ (A + B)), not each option's rate against all opportunities league-wide.

## Shot profile

| Tendency | Numerator | Denominator (real opportunity count) |
|---|---|---|
| Three-Point Attempt Rate | 3PA | FGA |
| Mid-Range Attempt Rate | Mid-range attempts | FGA |
| Rim Attempt Rate | Rim/Restricted-Area attempts | FGA |
| Catch-and-Shoot vs. Pull-Up (either/or) | Pull-up jumper attempts | Catch-and-shoot + pull-up jumper attempts (stats.nba.com's real "Catch and Shoot" and "Pull Up" dashboards) |
| Shot Clock Usage | FGA taken with 7 or fewer seconds left on the shot clock | Total FGA (a single direct rate — not a share against only the earliest bucket, so no real data is discarded) |

## On-ball creation / usage

| Tendency | Numerator | Denominator |
|---|---|---|
| Isolation Frequency | Isolation possessions (stats.nba.com Play Type dashboard — a directly-published frequency) | Total offensive possessions used |
| Post-Up Frequency | Post-up possessions (same Play Type dashboard) | Total offensive possessions used |
| Pick-and-Roll Usage (as ball-handler) | Ball-handler PnR possessions (same Play Type dashboard) | Total offensive possessions used |
| Drive-and-Kick vs. Drive-to-Finish (either/or) | Passes thrown off a tracked drive | Passes thrown off a drive + shot attempts off a drive (stats.nba.com's real "Drives" dashboard — both are published columns on it) |
| Pass-First vs. Score-First / Shot-Hunting | Passes Made | Touches (stats.nba.com's real "Touches" tracking dashboard) |
| Foul/Contact-Seeking | FTA | FGA |

## Off-ball movement

| Tendency | Numerator | Denominator |
|---|---|---|
| Cutting Frequency | Cut possessions (Play Type dashboard) | Total offensive possessions used |
| Screen-Setting Willingness | Screen Assists (official Hustle Stats) | Team offensive possessions played while this player was on the floor |

## Defensive approach

| Tendency | Numerator | Denominator |
|---|---|---|
| Gamble-for-Steals Frequency | Deflections (official Hustle Stats — the NBA's own definition already encompasses both successful-steal and non-steal deflections, so using Deflections alone avoids double-counting Steals, which belongs to the Steals attribute's success-rate measure instead, not this tendency) | Defensive possessions played |
| Help Defense Aggressiveness | HELP_FGA (opponent field goal attempts defended in a help capacity, per stats.nba.com's real Matchup dashboard) | MATCHUP_FGA + HELP_FGA (total opponent attempts defended in any capacity) |
| Defensive Foul Aggression | Personal fouls committed | Defensive possessions played |

## Hustle / effort

| Tendency | Numerator | Denominator |
|---|---|---|
| Offensive Rebound Crash Rate | Offensive Rebound Chances (stats.nba.com's real Rebounding tracking dashboard — not Hustle Stats; corrected from an earlier draft) | Team missed FGA while this player was on the floor |
| Defensive Rebound Box-Out vs. Leak-Out | Box Outs (official Hustle Stats) | Team defensive-rebound situations while this player was on the floor (i.e. opponent FGA + FTA-ending-in-a-miss while on court) — "leak-out" is the implicit complement (1 − this rate), not an independently measured count |
| Fast Break Leak-Out | Transition/fast-break possessions (Play Type dashboard) | Total offensive possessions used |
| Loose Ball / Floor Dive Willingness | Loose Balls Recovered (official Hustle Stats) | Total possessions (offensive + defensive) played |
| Charge-Taking Willingness | Charges Drawn (official Hustle Stats) | Defensive possessions played |

## Parked — not computed in Phase 1, for a specific real reason

Three tendencies from the original draft list are **cut from Phase 1**, not faked with an invented proxy. Each hits the same kind of wall already acknowledged elsewhere in this design (the possession-engine doc's "one hard limit": full defender-contest geometry is proprietary data that was never made public). Parking these is the honest move, consistent with that precedent, rather than forcing a formula onto data that doesn't exist:

- **Closeout Aggressiveness** — the original definition needed closest-defender-distance data *from the defender's own perspective* (how tight was his specific closeout), but the public closest-defender-distance tracking only exists from the *shooter's* side (how a shooter performs by distance-of-whoever-was-closest, not tied back to a specific defender's positioning choice). The real signal that does exist here — opponent 3PT efficiency allowed when this player is the primary matchup — already lives inside the On-Ball Defense **attribute**, so this doesn't disappear from the design, it just isn't a separate tendency on top of it.
- **Screen Navigation: Over vs. Under** — requires knowing, per ball-screen event, whether the defender fought over or went under. Public play-by-play doesn't record ball-screen events at that level of detail at all (only aggregate play-type frequency exists), so there's no real sequence to measure this from.
- **Switch Willingness** — requires tracking which specific defender was assigned to the ball-handler immediately before and after each screen. The public Matchup dashboard only publishes season-aggregate matchup totals, not possession-level assignment changes, so this can't be reconstructed from public data either.

If a future data source changes this (e.g. licensed Second Spectrum access), these three can be added back using the same methodology as everything else here — real stat, real opportunity count, Beta-Binomial shrinkage.

## Sources
- stats.nba.com public tracking dashboards: Play Type (Synergy-powered), Catch and Shoot / Pull Up, Drives, Touches, Shot Clock, Rebounding, Matchup
- NBA official Hustle Stats: Screen Assists, Deflections, Loose Balls Recovered, Charges Drawn, Box Outs
