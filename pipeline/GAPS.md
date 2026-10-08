# Phase 1: open questions and mechanical readings

The revised docs 01-06 and 11 resolve every earlier gap (G1-G23, F1-F7, O1): the 0-99 mapping, the
shot buckets, the expectation models, the blending rules, position labels, the tendency
denominators, and the trait definitions. Everything below is either an **open question** (the
docs leave a real choice, so the build stops and names it if real data hits it) or a **mechanical
reading** (a detail the docs leave implicit where only one reading is consistent with them,
listed so you can overrule any of them).

## Open questions (Q)

### Q1. Offensive Load per100 can be negative (doc 02, Shared stat definitions; Ball Handle)
Box Creation's constant (-1.1942) makes Offensive Load negative for a player with almost no box
stats (e.g. 0 FGA, 0 AST, 0 TOV in a few possessions). Ball Handle shrinks "Offensive Load per100"
with S2 (Gamma-Poisson), which is undefined for a negative count, and E3 uses
`ln(Offensive Load per100)`. **Build behaviour:** if any player with exposure has a negative load,
Ball Handle, Offensive IQ and Consistency (which clusters on it) stop with the player list. Needs a
rule in the doc if it happens.

### Q2. Box Creation per100 in Offensive IQ has no shrinkage family (doc 02, Offensive IQ item 6)
The section says each component is "a z-scored shrunk statistic", but item 6 names no family, and
Box Creation can be negative, so S2 does not apply. **Build behaviour:** the formula exactly as
written, from raw per100 box terms, unshrunk. Confirm or name a shrinkage.

### Q3. Foul-cost allocation when a player has no contests (doc 02, Foul cost)
The perimeter/rim shares are `(A_P3+A_P2)/A_overall` and `A_R/A_overall`. For a player with
defensive possessions but zero closest-defender attempts this is 0/0. **Build behaviour:** On-Ball
Defense and Rim Protection stop with the player list. Needs a rule if it happens.

## Mechanical readings

Population and scales
1. Population = rostered players with a positive possession estimate on both offense and defense.
   Priors are fit on that population (players with opportunities > 0 for that statistic).
2. `Z(x) = Phi^-1(pct(x))` wherever a doc writes `Z(...)`; the standard score `(x - mean)/SD` wherever
   it writes lower-case `z(...)` (Physicals, Stamina's distance term) and for trait SDs (doc 04).
3. Possessions: `FGA - OREB + TOV + 0.44 FTA` from the on-floor counts.

Expectation models and regressions
4. Logistic ridge follows sklearn's convention `C = 1/lambda`; least-squares ridge penalizes
   `lambda * ||beta||^2` on the weighted sum of squares. Intercepts are unpenalized.
5. CV folds: games assigned round-robin in sorted order (5 folds); for the combine-test ridge,
   players in roster order round-robin. Grid for the combine-test ridge: doc 02's 21-value grid.
6. Stint ridge rows: one per (stint, team on offense), weight = that team's possessions in the
   stint; rows with no positive possession estimate carry no weight. Points variant y = points per
   100; shot-quality and rim variants read each FGA's zone and SHOT_DISTANCE from the shot chart
   (joined by game + event id).
7. Defensive IQ's Rule A target is the negated defense coefficient (higher = better), matching the
   orientation of its components. Rule A centers target and components (a free intercept).
8. E3 covariates use the shrunk per100 values (Offensive Load*, creation possessions*); Passing
   Accuracy's risk covariate is the raw `POTENTIAL_AST / PASSES_MADE`. Decision-turnover exposure is
   OFFPOSS. A player with no exposure for an E3 model gets RR* = 1.
9. Vision's assisted-shot quality: league mean and variance of u over all assisted made shots.
   Shot-choice value: league mean and variance of u over all FGA.
10. E5 blocks per category come from play-by-play, classified by the play-by-play shot value and
    distance (R < 6 ft, P3 = threes, P2 = other twos).
11. Stamina's per-player logistic has an intercept plus the slope on continuous minutes; the MLE
    does not exist for one outcome only, no spread in minutes, or separation, and those players
    take the prior mean. Continuous minutes restart at each period. Stint length's sampling
    variance uses the pooled within-player variance. Both S3s shrink toward the estimated mean.
12. phi-bar (FOUL%) is the population mean of the shrunk phi*. f-bar counts only regular free
    throws after a shooting foul (technical, flagrant and clear-path free throws excluded).
13. Post Defense "league PPP" = sum of PTS / sum of POSS over every player in the dashboard.
14. Off-Ball help contests: OLS of the S2 contested-shots per100 on the S2 D_FGA per100, with intercept.
15. Physicals: combine features are listed height, listed weight, final wingspan, roster AGE and the
    published position one-hot (seven labels). Tracking residuals: OLS on position one-hot, roster
    AGE and the player's final team's PACE. Distance per 48 = 48 x (DIST_MILES_OFF + DIST_MILES_DEF)
    / SpeedDistance MIN, unshrunk. Above-rim finishing residual: OLS on height + position one-hot.
16. Drives per100 in the Acceleration residual is the S2 value.

Tendencies
17. Mid-range and rim rates take both numerator and FGA from the shot chart; every other FGA is the
    box-score total. "All play-type possessions used" = sum of POSS over the 11 Synergy play types.

Traits
18. Durability: a box-score row counts as a DNP when its minutes are blank/0 and it has a comment;
    a comment containing "Coach's Decision" is not a missed game. Inactive list = missed. Roster
    games are counted per (player, team, game) over regular-season games.
19. Consistency features: shrunk values where a shrinkage is defined (Offensive Load* S2; 3PA rate*
    and rim rate* = the tendencies; BLK%* and STL%* S1; AST% and TRB% also S1). GMM: full
    covariance, `random_state = 0`.
20. Clutch: mu = sum PTS / sum TSA over all 2025-26 player-games; players with no clutch or no
    non-clutch attempts take the prior mean.
21. Streaky: shots ordered by game date, game, period, clock (descending), event id. With one make
    and one miss the runs-test variance is 0 and R always equals mu, so z = 0.
22. Tier boundaries: z >= 2 strong, 1 <= z < 2 mild (and the mirror image below).

Data
23. LeagueDashPtDefend publishes each category with its own columns (`FG3M/FG3A/NS_FG3_PCT`,
    `FG2M/FG2A/NS_FG2_PCT`, `FGM_LT_06/FGA_LT_06/NS_LT_06_PCT`); the build accepts those or the
    `D_FGM/D_FGA/NORMAL_FG_PCT` names. The doc 02 checklist assertions run in every build and are
    stored in the `data_checks` table.
24. Turnover taxonomy matches subtype text (plus liveData's descriptor, e.g. "out-of-bounds" +
    "bad pass"); every type seen is printed by the build with its class.
