
# Trait System

## Core mechanism

A trait is not a flag you either have or don't — it's a **spectrum with "no trait" as the neutral middle**, matching league average. A player only gets a named trait when their real, underlying value for that dimension is far enough from league average (measured in standard deviations) to stand out in either direction.

Standard shape, same for every trait (5 positions):
- 2+ SD below average → strong negative tier
- 1–2 SD below → mild negative tier
- within ~1 SD → **no trait** (most players)
- 1–2 SD above → mild positive tier
- 2+ SD above → strong positive tier

Nothing here is hand-picked: the SD thresholds are a standard statistics convention, and which bucket a player falls into is purely a function of their real, derived data. Tier rarity falls out automatically — e.g. "Iron Man" is naturally uncommon because being 2+ SD from average is uncommon by definition, not because rarity was separately tuned.

## Hard rule: every trait must have a real statistical proxy to measure against

No trait exists without real data to ground it. Candidates considered and explicitly rejected for having no statistical shadow: Work Ethic, Ambition, Coachability — these could potentially live in a separate, explicitly different "personality" system later (not data-driven), but do not belong in this trait mechanism.

## Locked trait list — every formula fully specified, nothing left to interpretation

- **Durability** — real games missed vs. games scheduled, **over a trailing 3-season window** (not a single season, which is too small a sample to distinguish injury-prone from unlucky-once, and not full career, which is undefined for a rookie). A player with fewer than 3 real seasons uses career-to-date; the empirical-Bayes shrinkage below (same mechanism as everywhere else) naturally pulls a short career's estimate toward league average rather than needing a separate special case.
  Tiers: Hospitalized — Injury Prone — (no trait) — Sturdy — Iron Man

- **Consistency** — real game-to-game statistical variance vs. league-average variance for *similar players*, where "similar" is players sharing the same primary role tag from the tactics doc's role taxonomy (a Spot-Up Shooter is compared to other Spot-Up Shooters, an Anchor Big to other Anchor Bigs) — reuses the role system already locked rather than inventing a separate grouping.
  Tiers: Erratic — Inconsistent — (no trait) — Steady — Metronome

- **Clutch** — two-level computation, not a single comparison:
  1. **The signal**: each player's own real clutch-situation stats (NBA's official clutch definition: last 5 minutes of the 4th quarter/OT, score within 5 points), compared against **that same player's own normal (non-clutch) stats** — a self-referential delta, not a comparison to league average. This is deliberate: clutch is about whether *this player specifically* performs differently under pressure, not whether he's good in an absolute sense late in games.
  2. **The tier**: that self-delta (clutch output minus normal output, on the same real stat basis — e.g. true shooting % swing) is then compared against the **league-wide distribution of every player's own self-delta** to find how many SDs from the league-typical delta (usually near zero) this player sits. A player whose self-delta is 2+ SD worse than the league-typical delta is "Rattled"; 2+ SD better is "Ice in His Veins."
  Tiers: Rattled — Shaky — (no trait) — Clutch — Ice in His Veins

- **Hustle** — a composite, computed via the same blending methodology as `02-attribute-derivation-formulas.md`'s "Blending weights" Rule B (equal-weighted z-score average — there's no independent external target to regress against here, same situation as the Strength attribute). Components, each standardized to a league-wide z-score and averaged with equal weight: Deflections, Loose Balls Recovered, Charges Drawn, Screen Assists, and Contested Shots rate (all real official NBA Hustle Stats, each expressed as a rate over the relevant on-court exposure) plus the player's own Gamble-for-Steals, Loose Ball/Floor Dive Willingness, Offensive Rebound Crash Rate, and Charge-Taking Willingness tendency values (already real, shrunk rates from `03-tendency-derivation-formulas.md`). The resulting composite z-score average is this trait's "real value," which is then SD-tiered against the league exactly like every other trait.
  Tiers: Lazy — Below Average — (no trait) — High Motor — Relentless

- **Streaky** — one specific, named test, not a choice between options: the **Wald–Wolfowitz runs test**, applied to each player's real, ordered sequence of makes/misses from real shot-log data (all shot attempts, ordered within and across games). The test produces a z-score for how non-random the sequence's clustering is versus what pure chance would produce — and because this z-score is already standardized against the random-chance null by construction, it maps directly onto this trait's SD-tier scale with no separate league-comparison step needed (unlike every other trait here, which needs a population reference to establish what "average" means — the runs-test null hypothesis *is* that reference).
  Tiers: Even-Keeled — Level — (no trait) — Streaky — Heat Check

## Minimum sample handling — resolved via empirical-Bayes shrinkage, same mechanism as attributes

Durability, Consistency, and Clutch all need enough real games/possessions before their underlying rate or variance estimate is trustworthy. Rather than a hand-picked "games played" threshold:
- **Durability** (a real proportion — games missed ÷ games scheduled) uses the same **Beta-Binomial empirical-Bayes shrinkage** as attribute rate stats, with the prior fit via method-of-moments on the real league-wide distribution of the stat.
- **Consistency and Clutch** (both variance/delta estimates, not simple proportions) use a **Scaled-Inverse-Chi-Squared (Inverse-Gamma) prior on variance**, fit the same way via method-of-moments on the real league-wide (or same-role, for Consistency) distribution of per-player variances/deltas.
- **Streaky**'s runs-test z-score is inherently sample-size-aware already (the test's own variance term accounts for sequence length), so it needs no separate shrinkage step — a short sequence naturally produces a z-score close to zero (no claim of streakiness) rather than a false extreme.

A rookie's three-game sample gets pulled hard toward the role/league-average value under all of the above; a ten-year veteran's estimate is trusted almost as observed. No player is excluded or given a placeholder — thin samples simply can't produce an extreme tier, because the real math won't let them.
