
# Trait System

## Core mechanism

A trait is not a flag you either have or don't — it's a **spectrum with "no trait" as the neutral middle**, matching league average. A player only gets a named trait when their real, underlying value for that dimension is far enough from league average (measured in standard deviations) to stand out in either direction.

Standard shape, same for every trait (5 positions):
- 2+ SD below average → strong negative tier
- 1–2 SD below → mild negative tier
- within ~1 SD → **no trait** (most players)
- 1–2 SD above → mild positive tier
- 2+ SD above → strong positive tier

**How a trait value becomes SDs.** For every trait except Streaky, each player's final (shrunk) value `x_i` is converted to `z_i = (x_i − mean(x)) / SD(x)` across the whole population (for Consistency, within the player's peer cluster). The tier is read from `z_i` (positive = the better end of the trait). Nothing here is hand-picked: the SD thresholds are a standard statistics convention, and which bucket a player falls into is purely a function of real, derived data. Rarity falls out automatically.

## Hard rule: every trait must have a real statistical proxy to measure against

No trait exists without real data to ground it. Candidates considered and explicitly rejected for having no statistical shadow: Work Ethic, Ambition, Coachability — these could potentially live in a separate, explicitly different "personality" system later (not data-driven), but do not belong in this trait mechanism.

## Locked trait list — every formula fully specified, nothing left to interpretation

- **Durability** — **availability**, derived from real game logs, over a **trailing 3-season window** (2023-24, 2024-25, 2025-26). A player with fewer than 3 real seasons uses career-to-date; the shrinkage below pulls a short career toward league average without a special case.
  - *Roster games* = team games in which he appears for that team, either in the box score (including DNP rows) or on that game's inactive list.
  - *Games missed* = roster games in which he is on the inactive list, or in the box score with a DNP comment other than "Coach's Decision". Coach's-decision DNPs are excluded because they are a choice about playing time, not availability; rest, injury and suspension are all counted, because the sim needs availability, not a diagnosis.
  - Rate = games missed ÷ roster games (Beta-Binomial, S1 in doc 02). Higher shrunk rate = worse.
  - Data: box scores (BoxScoreTraditional with the DNP `COMMENT`) and `BoxScoreSummaryV2` inactive-player lists for every game of the three seasons; `--smoke` verifies the inactive list and comment fields exist. `balldontlie.io` injury history is a supplement only and does not feed the number.
  Tiers: Hospitalized — Injury Prone — (no trait) — Sturdy — Iron Man

- **Consistency** — game-to-game variance of one defined per-game number, compared with players of the same kind.
  - *Per-game number:* Game Score per minute (Hollinger: `PTS + 0.4·FGM − 0.7·FGA − 0.4·(FTA − FTM) + 0.7·ORB + 0.3·DRB + STL + 0.7·AST + 0.7·BLK − 0.4·PF − TOV`, divided by minutes) in games with at least 10 minutes.
  - *Peer clusters (replacing the role-tag comparison):* the tactics-doc role tags are assigned by the sim and cannot be derived before it runs, so peers are statistical. Fit Gaussian mixture models with k = 2…12 clusters on standardized features (height; published position as its ordinal index G=1, G-F or F-G=2, F=3, F-C or C-F=4, C=5; Offensive Load per100; 3PA rate; rim-attempt rate; AST% = assists ÷ teammates' made field goals while he is on the floor; TRB% = his rebounds ÷ all rebounds (both teams) while he is on the floor; BLK% and STL% as defined in doc 02), choose k by lowest BIC, and assign each player to his highest-probability cluster. The clustering is refit whenever the pipeline runs.
  - *Variance and shrinkage:* each player's sample variance `s_i²` over `n_i` games is shrunk toward the cluster's variance with a Scaled-Inverse-Chi-Squared prior (`ν₀` and `s₀²` by method of moments on the cluster's per-player variances): `s_i²* = (ν₀·s₀² + (n_i − 1)·s_i²) / (ν₀ + n_i − 1)`.
  - Trait value = −`ln s_i²*`, converted to SDs within the cluster (higher = steadier).
  Tiers: Erratic — Inconsistent — (no trait) — Steady — Metronome

- **Clutch** — two-level computation, not a single comparison:
  1. **The signal**: each player's own real clutch-situation output (NBA's official clutch definition: last 5 minutes of the 4th quarter/OT, score within 5 points; `LeagueDashPlayerClutch`) compared against **that same player's own non-clutch output** (full-season totals minus clutch totals) — a self-referential delta. On the stated stat basis, **points per true-shooting attempt** (`PTS ÷ (FGA + 0.44·FTA)`): `d_i = PPTSA_clutch − PPTSA_non-clutch`, with sampling variance `s_i² = σ²·(1/TSA_clutch + 1/TSA_non-clutch)`, where `TSA = FGA + 0.44·FTA` and `σ²` is the **per-attempt** variance of points, estimated by the ratio-estimator residual variance over every player-game in the league: `σ² = Σ_g (PTS_g − μ·TSA_g)² ÷ Σ_g TSA_g`, with `μ` the league mean points per true-shooting attempt.
  2. **The tier**: `d_i` is shrunk with the Normal-Normal rule (S3 in doc 02, with the prior mean set to the league's mean delta, estimated, not assumed zero), and then converted to SDs against the league-wide distribution of every player's shrunk self-delta. 2+ SD worse than league-typical is "Rattled"; 2+ SD better is "Ice in His Veins."
  Tiers: Rattled — Shaky — (no trait) — Clutch — Ice in His Veins

- **Hustle** — a composite using Rule B of `02-attribute-derivation-formulas.md` (equal-weighted z-score average — no independent external target exists). **Each underlying statistic enters exactly once, as its shrunk value.** Components:
  1. Deflections per100 DEFPOSS (S2)
  2. Loose balls recovered per100 total possessions (S2)
  3. Charges drawn per100 DEFPOSS (S2)
  4. Screen assists per100 OFFPOSS (S2)
  5. Contested shots share = `CONTESTED_SHOTS ÷ opponent FGA while on the floor` (S1)
  6. Offensive-rebound crash rate = `OREB_CHANCES ÷ team missed FGA while on the floor` (S1)
  The earlier version also averaged in the Gamble-for-Steals, Loose Ball, Charge-Taking and Crash tendency values, which are the same statistics as components 1, 2, 3 and 6, so they were counted twice with double weight. Those tendencies still exist in `03-tendency-derivation-formulas.md` as how often he does it; this trait just reads the shrunk statistics once.
  Tiers: Lazy — Below Average — (no trait) — High Motor — Relentless

- **Streaky** — one specific, named test: the **Wald–Wolfowitz runs test**, applied to each player's real, ordered sequence of field-goal makes and misses (all FGA, ordered by game date, period and game clock, concatenated across games; free throws excluded). With `n₁` makes, `n₂` misses and `R` runs, `z_runs = (R − μ) / σ` with `μ = 2n₁n₂/(n₁+n₂) + 1` and `σ² = (μ − 1)(μ − 2)/(n₁ + n₂ − 1)`. Fewer runs than chance means clustering, so **Streakiness z = −z_runs** (positive = more streaky). If `n₁ = 0` or `n₂ = 0` the z is 0. Because this z is already standardized against the random-chance null, it maps directly onto the SD-tier scale with no population reference needed.
  Data: ShotChartDetail with game date, period and clock.
  Tiers: Even-Keeled — Level — (no trait) — Streaky — Heat Check

## Minimum sample handling — resolved via empirical-Bayes shrinkage, same mechanism as attributes

- **Durability** (a proportion) uses Beta-Binomial shrinkage with the prior fit via method-of-moments on the real league-wide distribution.
- **Consistency** (a variance) uses a Scaled-Inverse-Chi-Squared prior on variance, fit per peer cluster.
- **Clutch** (a difference with a known sampling variance) uses the Normal-Normal rule.
- **Hustle**'s components are shrunk individually (S1/S2) before they are averaged.
- **Streaky**'s runs-test z-score is inherently sample-size-aware, so it needs no separate shrinkage: a short sequence produces a z near zero.

A rookie's three-game sample gets pulled hard toward the cluster/league-average value under all of the above; a ten-year veteran's estimate is trusted almost as observed. No player is excluded or given a placeholder — thin samples simply can't produce an extreme tier, because the real math won't let them.
