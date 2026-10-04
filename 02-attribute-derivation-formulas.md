
# Attribute Derivation Methodology

## Hard rule, same discipline as the trait system

Attribute values are a pure function of real statistical inputs, computed the same way for every player with no exceptions. **No reputation, name recognition, media narrative, draft pedigree, or subjective "impression" of a player may factor into a derived attribute value, in any amount, ever.** Two players with identical underlying statistical profiles get identical attributes, full stop — one being famous and one being obscure changes nothing. This mirrors the trait system's existing hard rule ("every trait must have a real statistical proxy") extended explicitly to attributes, since that constraint was always implicit in this design but never stated as its own rule.

## The four-step pipeline, applied to every attribute

1. **Identify the real stat(s) that actually measure this one attribute** — not an adjacent or convenient one, and preferring an existing, already-named real stat over a hand-rolled blend wherever one actually exists.
2. **Adjust for volume** — fully specified below, not a hand-picked cutoff.
3. **Adjust for difficulty where real difficulty data exists.** Raw make-rate conflates skill with the difficulty of what was attempted. Public shot-tracking data (stats.nba.com's shooting splits by closest-defender distance, shot clock state, and play type) lets several attributes be computed against *expected* performance for that shot type/difficulty, not just the raw percentage. Flagged per-attribute below where this applies.
4. **Convert to a league percentile, then map through the locked non-linear curve** from the attribute doc (steep through the normal range, compressed at the extremes) to get the final 0-99 value. For a few attributes (noted below) the percentile comparison is against same-role players, not the whole league undifferentiated, reusing the role taxonomy the same way Consistency's trait definition does.

## Volume adjustment, fully specified: empirical Bayes shrinkage with the prior fit from real league data

There is no separate hand-picked games/attempts cutoff anywhere in this design. Instead, every volume-sensitive stat uses **empirical Bayes shrinkage, where the shrinkage prior's shape is itself estimated from the real league-wide data** — not chosen by hand.

**Beta-Binomial is the default, used for every stat that is already a real proportion of a well-defined opportunity count** — not just literal make/attempt stats (FG%, 3P%, FT%), but also stats like ORB%, DRB%, and STL%, which are standard basketball rate stats already defined as a count of successes against a count of real, countable chances (e.g. ORB% = offensive rebounds ÷ total available rebounds — offensive boards plus the opponent's defensive boards — while this player was on the floor). Fit a **Beta(α, β) prior** to the real league-wide distribution of that proportion via method-of-moments — take the mean and variance of the observed per-player rates, correct the observed variance by subtracting the average binomial sampling noise (mean of `p·(1-p)/n` across players), and solve the standard two equations for α and β from the corrected mean/variance. A specific player's shrunk rate is then `(successes + α) / (opportunities + α + β)`. This is the same method David Robinson's canonical empirical-Bayes treatment of baseball batting averages uses, applied to basketball rate stats instead.

**Gamma-Poisson is the exception, reserved specifically for genuine points-per-possession stats** (Post Scoring, Post Defense) where the real quantity isn't a yes/no proportion — a single possession can produce 0, 2, or 3 points, not just a success/failure — so a count-per-exposure model fits what the stat actually is, rather than forcing it into a binomial shape it doesn't have. Fit a **Gamma(k, θ) prior** the same way via method-of-moments on the real league-wide per-player rate distribution, corrected for Poisson sampling noise. A specific player's shrunk rate is `(points scored + k) / (possessions + k/θ)`. **cTOV%**'s turnover-count numerator (over the Offensive Load exposure denominator, not a simple trial count) is the one Playmaking exception that also uses this model, for the same reason — Offensive Load is a composite exposure measure, not a count of discrete yes/no trials.

**For variance estimates** (the trait system's Consistency, Clutch, and Streaky, which measure how much a player's own output varies or differs rather than a single rate): the analogous **Scaled-Inverse-Chi-Squared (Inverse-Gamma) prior on variance**, fit via method-of-moments on the real league-wide (or role-wide, for Consistency specifically) distribution of per-player variances/deltas. Full detail lives in `04-player-trait-system.md`.

**Why this removes the need for a hard cutoff:** a hand-picked "player needs N attempts before we trust this" rule would itself be an invented, non-real number — exactly what this whole doc exists to avoid. Shrinkage derived this way is continuous and automatic: a rookie's 5 three-point attempts get shrunk almost all the way to league-average 3P%, which on its own makes an extreme tier or an extreme attribute value essentially unreachable from a small sample — not because a rule excluded him, but because the real math won't produce an extreme value from that little real signal. Every player always gets a computed value; thin samples just can't produce confident extremes.

## Measurables — not derived, pulled directly

Height, Wingspan, Weight: real biometric data, not computed from performance stats at all. Wingspan imputation for players missing a real measurement is a regression fit on real combine data (per `11-phase-1-3-build-and-data-pipeline-plan.md`), not a derived "attribute."

## Rim Scoring

| Attribute | Real stat(s) | Volume/difficulty handling |
|---|---|---|
| Driving Layup | FG% on live-dribble-drive layup attempts (shot-type + play-type tracking) | Beta-Binomial shrinkage (opportunity = drive layup attempts); compared against league expected FG% for shots of that distance/type as the difficulty baseline |
| Driving Dunk | Dunk conversion rate on drives (dunk attempts and makes off live-dribble drives) | Beta-Binomial shrinkage (opportunity = drive dunk attempts) |
| Standing Dunk | Assisted-dunk rate off cuts/off-ball situations (distinct play-type from drives) | Beta-Binomial shrinkage (opportunity = assisted-dunk-eligible looks) |
| Touch | FG% on the remaining non-drive, non-dunk attempts at the basket (post-up finishes, cuts, broken-play scrambles) **plus short push-shot/floater attempts specifically**, using stats.nba.com's real "In The Paint (Non-Restricted Area)" shot zone as the floater-distance source — this is a real, separately-tracked zone, distinct from Restricted Area attempts, so floaters aren't conflated with true rim shots | Beta-Binomial shrinkage (opportunity = that attempt bucket), difficulty-adjusted using closest-defender-distance shooting splits (public tracking data) — this is real touch skill isolated from pure strength/explosiveness |
| Post Scoring | Points-per-possession and FG% on post-up play-type possessions | Gamma-Poisson shrinkage for the PPP component (points over post-up possessions defended), Beta-Binomial for the FG% component (post-up frequency varies a lot by player, so shrinkage matters a great deal here either way) |

**Cross-check, not a sixth attribute:** overall **Rim FG%** (Restricted Area shooting percentage across every attempt type — a real, standard, named stat, e.g. databallr's `RIM FG%`) isn't a derived attribute of its own. It's a real number every player already has, and it exists here as a build-time sanity check: the frequency-weighted combination of Driving Layup, Driving Dunk, Standing Dunk, and Touch's rim-specific share should reconstruct a player's actual real Rim FG% closely. Same validation principle as the possession engine's mismatch-amplification check — the decomposed pieces need to add back up to the real whole, not just look independently plausible.

## Shooting

| Attribute | Real stat(s) | Volume/difficulty handling |
|---|---|---|
| Three Pointer | 3P%, split by catch-and-shoot vs. pull-up and by closest-defender distance | Beta-Binomial shrinkage per split (opportunity = attempts in that split), then combined weighted by the player's actual attempt mix |
| Mid Range | FG% on mid-range attempts, same catch-and-shoot/pull-up and defender-distance splits | Same as above |
| Free Throw | FT% | Beta-Binomial shrinkage (opportunity = FTA; least adjustment needed — free throws have no defender/difficulty variable) |

**Attempt-mix weighting uses real rate stats, not raw counts.** The "actual attempt mix" used to recombine the splits above is built from real zone-**rate** stats — **3PR (three-point rate = 3PA ÷ FGA)**, a standard, already-named real stat, for the three-point share, and the equivalent rim-attempt-rate and mid-range-attempt-rate shares (rim/mid attempts ÷ total FGA) for the other two zones. Using rates instead of raw attempt counts matters because a bench player's genuinely narrow shot diet shouldn't get diluted or distorted by simply having fewer total minutes than a starter — the rate stat represents what he actually does with the shots he takes, independent of how many minutes he was given.

## Playmaking

| Attribute | Real stat(s) | Confidence |
|---|---|---|
| Ball Handle | **sTOV% — Scoring Turnover Percentage: the share of turnovers committed specifically while attempting to score** (travels, discontinued-dribble violations, offensive fouls and strips taken mid-drive). A real, already-named stat (databallr) | Direct, Beta-Binomial shrinkage (opportunity = scoring attempts) — isolates handling breakdowns under scoring pressure specifically |
| Passing Accuracy | **PASSTOV — Passing Turnover Percentage: bad-pass turnovers ÷ (potential assists + bad-pass turnovers)**. A real, already-named stat (databallr) | Direct, Beta-Binomial shrinkage — the denominator already scales for how many passing opportunities the player had |
| Vision | Potential assists relative to actual assists, adjusted against the player's role (quantity layer, unchanged) — **plus Rim AST Share (assists that lead directly to a made basket at the rim ÷ total assists) as a quality layer**, a real, named stat (databallr's Rim AST, reframed here as a share of the player's own assists so it's a bounded, Beta-Binomial-compatible proportion rather than a per-100-possessions count) | Direct-ish, role-relative for the quantity half; Rim AST Share specifically rewards setting up the highest-value shot a playmaker can create, not just any created look |
| Ball Security | **cTOV% — Creation-adjusted Turnover Percentage: Turnovers per 100 possessions ÷ Offensive Load.** Both terms have exact, real, public formulas — see below | Direct, Gamma-Poisson shrinkage (Offensive Load is a composite exposure measure, not a simple trial count — see "Volume adjustment" above) |
| Shot Selection | The *quality* of shots taken (location/clock-state-implied expected value of the shot mix), compared to league-average efficiency by zone — this measures the choices, not the makes | Approximation using public shot-location data; databallr's ShotQuality RAPM decomposition is a useful cross-check once the pipeline is running |
| Offensive IQ | Regression-weighted blend — see "Blending weights" below | Weakest raw-signal attribute by nature (no single real stat measures "IQ"), but the blend weights themselves are no longer hand-picked — see below |

**Offensive Load and Box Creation — exact real formulas (Ben Taylor / Thinking Basketball), fully computable from standard box score data, no proprietary tracking required:**

```
3pt proficiency = (2 / (1 + EXP(-3PA)) - 1) * 3P%

Box Creation = Ast*0.1843 + (Pts+TOV)*0.0969 - 2.3021*(3pt proficiency)
               + 0.0582*(Ast*(Pts+TOV)*3pt proficiency) - 1.1942
               (Ast, Pts, TOV, 3PA all per-100-possessions)

Offensive Load = ((Ast - (0.38 * Box Creation)) * 0.75) + FGA + (FTA * 0.44) + Box Creation + TOV
               (all terms per-100-possessions)

cTOV% = Turnovers per 100 possessions / Offensive Load
```

**The turnover-adjacent overlap is resolved, not just acknowledged.** Real, separately-named stats exist for each distinct failure mode: a bad pass (PASSTOV), a breakdown while trying to score (sTOV%), and overall live-ball security scaled against creation burden (cTOV%). Each of the three now has its own direct real stat rather than sharing one hand-rolled signal.

## Defense

| Attribute | Real stat(s) | Confidence |
|---|---|---|
| Offensive Rebounding | ORB% = offensive rebounds ÷ (offensive rebounds + opponent defensive rebounds) while this player is on the floor — a real, standard, already opportunity-normalized stat | Direct, Beta-Binomial shrinkage |
| Defensive Rebounding | DRB% = defensive rebounds ÷ (defensive rebounds + opponent offensive rebounds) while this player is on the floor | Direct, Beta-Binomial shrinkage |
| Steals | STL% = steals ÷ opponent possessions while this player is on the floor — the standard, already-opportunity-normalized definition | Direct, Beta-Binomial shrinkage |
| On-Ball Defense | Opponent FG% when this player is the closest defender, by shot distance, compared against league-average FG% for shots of that type — a real, public, difficulty-adjusted defensive efficiency measure (stats.nba.com's defensive shooting-against and matchup data) | Direct, Beta-Binomial shrinkage (opportunity = opponent shots defended) |
| Off-Ball Defense | Regression-weighted blend — see "Blending weights" below. Components (deflection rate, loose-balls-recovered rate) are each real counts over defensive possessions played, same opportunity basis as the matching tendencies in `03-tendency-derivation-formulas.md` | Weaker raw signal by nature, blend weights no longer hand-picked |
| Post Defense | Opponent points-per-possession allowed on post-up play-type possessions defended by this player | Direct, Gamma-Poisson shrinkage (points over possessions defended) |
| Rim Protection | Opponent FG% at the rim when this player is the contesting defender, combined with block rate (blocks ÷ rim attempts contested) | Direct, Beta-Binomial shrinkage for both components |
| Defensive IQ | Regression-weighted blend — see "Blending weights" below | Weakest raw-signal attribute by nature, same treatment as Offensive IQ |

## Physicals

| Attribute | Real stat(s) | Confidence |
|---|---|---|
| Speed / Acceleration | Real in-game tracking data — average speed and distance traveled per game (public "Speed & Distance" tracking stats) | Covers every player who actually played, not just draft-combine attendees — better coverage than combine sprint times, used as the primary source |
| Lateral Quickness | Combine lane-agility drill time where available; in-game defensive-closeout/screen-navigation tracking as a secondary signal for players without combine data | Combine-only players need the same kind of fallback as wingspan |
| Vertical | Combine vertical-leap testing where available; dunk/contested-rebound rate as a secondary signal otherwise | Same combine-coverage gap as above |
| Strength | No strong direct public stat — regression-weighted blend, see below | Weakest-signal physical attribute, flagged honestly rather than papered over |
| Stamina | Performance decline across back-to-backs and across a single game's late minutes, from real rest-days and clutch/4th-quarter performance splits | A genuinely clever but still indirect real proxy — measures the *effect* of fatigue on output, not fatigue itself directly |

## Blending weights for multi-stat attributes: fit from data, never hand-picked

Four attributes (Offensive IQ, Defensive IQ, Off-Ball Defense, Strength) have no single clean real stat and are built from several real component stats. The blend weights across those components are never chosen by hand — they're set by one of two rules, chosen by whether a clean, independent real validation target exists:

**Rule A — regression-fit weights, used whenever an independent real target exists.** Compute the attribute's real component stats (the "process" numbers — e.g. for Offensive IQ: AST/TOV ratio, free-throw-drawing rate, secondary-assist rate), standardize each to a league-wide z-score, then fit an ordinary least-squares regression of a real, independent **outcome** measure against those standardized components. The regression coefficients, rescaled to sum to 1, become the blend weights — refit every time the full-league data pipeline refreshes, never a one-time guess.
- **Offensive IQ**'s regression target is **Offensive RAPM**, computed from the same play-by-play/lineup data the pipeline already pulls (not an external dependency) — deliberately *not* one of the blended components itself, to avoid the circularity the "Additional real cross-check metrics" section below warns about.
- **Defensive IQ**'s regression target is **Defensive RAPM**, computed the same self-hosted way.
- **Off-Ball Defense**'s regression target is **D-SQI** (databallr) — a real, lineup-isolated measure of shot-quality suppression, which is specifically what help defense and rotations are supposed to produce, making it a clean, non-circular target for components like deflection rate and loose-balls-recovered rate.

**Rule B — equal-weighted z-score average, used when no independent real target exists.** **Strength** has no publicly available standalone "strength impact" measure to regress against, so its components (post-up PPP under contact, free-throws-drawn-on-contact rate, contested-offensive-rebound rate) are standardized to league-wide z-scores and averaged with equal weight — the standard, bias-free way to combine several real signals of unknown relative importance without inventing a weighting scheme. (The Hustle *trait* in `04-player-trait-system.md` reuses this exact rule too.)

Both rules produce weights that come from real data (either a regression fit or a neutral equal-weight default), never a hand-picked number, and both are refit automatically as the pipeline's data grows.

## Additional real cross-check metrics (Phase 3 calibration, and regression targets above)

These are real, already-computed, lineup-level impact metrics (several from databallr, one from the independently maintained DARKO model). RAPM and D-SQI are used directly as regression targets above; all of them double as Phase 3 validation checks once the possession engine is running:

- **RAPM (Regularized Adjusted Plus-Minus)** — computable directly from the same play-by-play/lineup data the pipeline already pulls, not an extra data source. Used as the regression target for both IQ attributes above, and as a standing validation check afterward.
- **DPM (DARKO's Daily Plus-Minus)** — a maintained, public, all-in-one impact model (darko.app). An independent second opinion alongside self-hosted RAPM for Phase 3 validation.
- **D-SQI (Defensive Shot-Quality Influence) and Pts Saved/100** — real, lineup-isolated measures of how much a player actually suppresses opponent shot quality once teammates are accounted for (databallr). D-SQI is the Off-Ball Defense regression target above; Pts Saved/100 is an additional Rim Protection cross-check.
- **Six-Factor decomposition (oTS/dTS/oTOV/dTOV/oREB/dREB)** — lineup-adjusted splits isolating offensive/defensive shooting, turnover, and rebounding impact separately (databallr). A parallel check across several attributes at once during Phase 3 validation.

If a regression-weighted attribute's real-world tracking (via these metrics) drifts from what the possession engine produces once it's running, that drift — not a hunch — is what should trigger refitting the regression on fresher data, which the pipeline already does automatically on refresh.

## Sources
- [databallr Stats Glossary](https://databallr.com/stats/glossary) — Rim AST, 3PR, RIM FG%, sTOV%, PASSTOV, cTOV%, RAPM, D-SQI, Pts Saved/100, Six-Factor components
- [DARKO (darko.app)](https://darko.app) — DPM, public all-in-one impact model used as an independent cross-check
- [Thinking Basketball — "Offensive Load and Adjusted TOV%"](https://thinkingbasketball.net/2017/10/16/offensive-load-and-adjusted-tov/) — exact Offensive Load and cTOV% formulas (Ben Taylor)
- [Sal's Substack — "Intro to Ben Taylor's Passing Metrics"](https://salnba.substack.com/p/intro-to-ben-taylors-passing-metrics) — exact Box Creation formula, confirmed computable from standard box-score inputs
- David Robinson, *Introduction to Empirical Bayes: Examples from Baseball Statistics* — the Beta-Binomial method-of-moments shrinkage approach applied here to basketball rate stats
