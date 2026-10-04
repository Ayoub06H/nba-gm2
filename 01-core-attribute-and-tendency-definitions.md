# Attribute & Tendency System

Core design principle: attributes and tendencies are almost never used in isolation. Nearly every in-game outcome is a combination of several of these values, not a single lookup.

## Two separate systems

- **Attributes** — how *good* a player is at a skill (execution layer).
- **Tendencies** — how *often* a player chooses to do something, independent of whether it's wise (decision layer).

### How they interact (three-layer pipeline, not competing systems)

1. **Tendency** decides *what gets attempted* this possession (e.g., does the player gamble for a steal, shoot early in the clock, drive vs. pull up).
2. **IQ / Shot Selection** acts as a *quality gate* on that choice — given the game state, was this a good or bad moment to do the thing the tendency just picked. Same tendency value can produce very different outcomes depending on IQ (e.g., a high steal-gamble tendency paired with elite Defensive IQ = well-timed disruption; paired with poor Defensive IQ = reckless, out of position).
3. **Raw skill attribute** determines execution once the attempt happens (did the shot go in, was the finish successful, etc).

This resolves what would otherwise look like overlap between "IQ" attributes and tendencies: tendency is amoral/neutral about quality; IQ determines whether that tendency was deployed well in the moment.

## Attributes (locked)

### Measurables (raw data, not rated 0-99 — pure biometric inputs other calculations read from)
- Height
- Wingspan
- Weight

### Offense — Rim Scoring
- Driving Layup
- Driving Dunk
- Standing Dunk
- Touch
- Post Scoring

### Offense — Shooting
- Three Pointer
- Mid Range
- Free Throw

### Offense — Playmaking
- Ball Handle
- Passing Accuracy
- Vision
- Ball Security
- Shot Selection
- Offensive IQ

### Defense
- Offensive Rebounding
- Defensive Rebounding
- Steals
- Off-Ball Defense
- On-Ball Defense
- Post Defense
- Rim Protection
- Defensive IQ

### Physicals
- Speed
- Acceleration
- Lateral Quickness
- Vertical
- Strength
- Stamina

### Explicitly rejected as standalone attributes (resolved as combinations instead)
- Screen Setting (skill) — not modeled; screen-setting *willingness* lives as a tendency instead, quality comes from Strength + Offensive IQ
- Hands / Lob Finishing — not modeled as its own stat; emerges from Vision/Passing Accuracy (passer) + Driving Dunk + Height/Weight/Vertical (finisher)
- Shot Off-Dribble vs. Off-Catch as a *skill* — not modeled as separate skills; resolved as a tendency (how often each is attempted), with quality determined by combining Shooting + Ball Handle + Shot Selection

## Tendencies (locked list — full derivation methodology now in `03-tendency-derivation-formulas.md`)

### Shot profile
- Three-Point Attempt Rate
- Mid-Range Attempt Rate
- Rim Attempt Rate
- Catch-and-Shoot vs. Pull-Up
- Shot Clock Usage (early vs. late in clock)

### On-ball creation / usage
- Isolation Frequency
- Post-Up Frequency
- Pick-and-Roll Usage (as ball-handler)
- Drive-and-Kick vs. Drive-to-Finish
- Pass-First vs. Score-First / Shot-Hunting
- Foul/Contact-Seeking

### Off-ball movement
- Cutting Frequency
- Screen-Setting Willingness (behavioral — effort/sacrifice, not skill)

### Defensive approach
- Gamble-for-Steals Frequency
- Help Defense Aggressiveness
- Defensive Foul Aggression

### Hustle / effort
- Offensive Rebound Crash Rate
- Defensive Rebound Box-Out vs. Leak-Out
- Fast Break Leak-Out
- Loose Ball / Floor Dive Willingness
- Charge-Taking Willingness

### Parked — not computed in Phase 1 (see `03-tendency-derivation-formulas.md`'s "Parked" section for the exact reason each one hits a real public-data wall)
- ~~Closeout Aggressiveness~~ — folded into the existing On-Ball Defense attribute instead; no separate public signal exists for "how often he closes out tight" independent of outcome
- ~~Screen Navigation: Over vs. Under~~ — public play-by-play doesn't record ball-screen events at the needed granularity
- ~~Switch Willingness~~ — public matchup data is season-aggregate only, not possession-level assignment tracking

## Scale decision (locked)

Three separate concerns, decoupled rather than solved by picking one scale:

1. **Internal precision** — store a high-resolution value (float, or an internal 0-999 scale) that nothing rounds early. Needed because real-player calibration will fit attributes against continuous NBA statistical percentiles — rounding early would throw away real signal before it's even used.
2. **Outcome curve shape** — this is what actually makes two values "feel different," not the scale. A non-linear (sigmoid/logistic-style) attribute→probability mapping, steep through the normal range and compressed at the extremes, means a gap like 87 vs. 80 can matter a lot or very little depending on where it sits in the distribution — which mirrors how real skill gaps work (a few points separates "very good" from "unguardable" near the top; the same numeric gap in the mushy middle means less).
3. **Display scale** — decided last, and least important once 1 and 2 are solid. Chosen: **0-99 for display**, since it gives finer resolution for comparing players and matches the precision available from real-stat calibration. (0-20-style coarser display was considered but rejected as the fix for "values should feel different" — that problem belongs to the curve shape, not scale granularity. A coarser scale may still be worth revisiting later purely as a scouting/fog-of-war presentation choice, separate from this decision.)

Tendencies use a related but simpler scale, specified in `03-tendency-derivation-formulas.md`: a direct 0-1 real rate (Beta-Binomial-shrunk, not percentile-mapped or curve-reshaped), since a tendency already is a frequency rather than a skill level.

## Still open — and why neither item blocks Phase 1

- **Whether every tendency listed above survives pruning**, or some turn out to be redundant once combination math is actually built. Every tendency has a real, computable stat behind it regardless (see `03-tendency-derivation-formulas.md`), so this is a post-hoc simplification question for Phase 2, not a derivation gap — Phase 1 computes all of them.
- **Exact numeric shape/parameters of the non-linear attribute→probability curve** (steepness, inflection point) — this is not an unresolved design question, it's a Phase 1 *build step*: the curve is fit against the real percentile distribution once the full league's real attribute data is actually loaded, the same way the curve for any calibrated model is fit against its real data rather than guessed beforehand. Nothing here is left for Claude Code to invent — the shape (sigmoid-family, steep-middle/compressed-tails) is locked; only its specific numeric parameters wait on having the real distribution to fit against, which Phase 1 itself produces.
