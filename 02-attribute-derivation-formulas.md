
# Attribute Derivation Methodology

## Hard rule, same discipline as the trait system

Attribute values are a pure function of real statistical inputs, computed the same way for every player with no exceptions. **No reputation, name recognition, media narrative, draft pedigree, or subjective "impression" of a player may factor into a derived attribute value, in any amount, ever.** Two players with identical underlying statistical profiles get identical attributes, full stop.

There are **27 rated attributes** (plus 3 unrated Measurables). Ball Security and Shot Selection were removed: turnover avoidance lives inside Ball Handle and Passing Accuracy (load-adjusted), and the quality of a player's shot choices is one component of Offensive IQ. **Shot Blocking** is a rated attribute of its own (the engine resolves a block as a distinct event before the miss).

## The design idea: every skill answers "how well" and "how much"

An efficiency-only rating rewards sheltered low-volume players and punishes players who do the hard version of a skill at scale. A volume-only rating rewards chuckers. So wherever both questions are meaningful, a rating uses both:

- **How well** — efficiency *relative to what the same shots/situations are expected to yield* (difficulty- or load-adjusted), shrunk for small samples.
- **How much** — how often he does it per 100 team possessions he is on the floor (volume/load), shrunk for small samples.

Where one question is meaningless, only the other is used and the reason is stated in that attribute's row. **Defensive attributes that are about preventing shots are rated in net points saved per 100 possessions** (opponent points below what the same shots were expected to produce, minus the cost of fouls), because there "how well × how much" is one natural product and a defender who is rarely tested is simply average.

**Known trade-off, flagged deliberately:** putting volume inside a rating means a high-volume player gets credit both in his tendency (he chooses it often) and in his attribute (he is rated higher). Real basketball has the same selection effect, but Phase 3's validation against the real season is where any resulting over-inflation should be checked and, if needed, corrected by refitting the efficiency/volume split. The same applies to the deliberate overlaps listed in "Known overlaps" at the end.

## Reuse rule: one statistic may inform several attributes

Real statistics overlap, and a statistic that genuinely says something about two skills is used in both. The only constraints are: (1) a statistic feeds an attribute only if it is real evidence of that skill; (2) every attribute keeps at least one component that no other attribute in its group uses, so attributes stay distinct; (3) Phase 3 checks that no two attributes are nearly the same number (pairwise correlation above about 0.9 is flagged and reviewed). Overlaps are listed under "Known overlaps". One limit: an attribute that is already an all-in points-saved number (On-Ball Defense, Post Defense, Rim Protection) does not get extra stats about the *same* outcome added in other units, because that would count the same points twice inside one number.

## Shared definitions

**Population.** Every player on a 2025-26 roster who logged at least one team possession on the floor (offense for offensive attributes, defense for defensive ones). **Rostered players with no exposure** (they never played) are not ranked with the others. **Temporary decision:** every rated attribute for such a player is set to the fixed placeholder **40.0**, and he is flagged `no_data = true` and `placeholder_rating = true`. This is the one deliberate exception to the no-hardcoded-values rule; it exists so the roster is complete and is to be replaced by the prior-value method (each shrunk component at its prior, his Score inserted into the exposed players' distribution without moving anyone else) when a player with no data needs a principled number, for example when scouting (doc 10) is built. Measurables and any combine tests he has are kept as real data. Tendencies get the prior rate; traits get no trait (z = 0).

**Exposure.** `OFFPOSS_i` / `DEFPOSS_i` = team offensive / defensive possessions while player *i* was on the floor (from play-by-play plus substitution data). `per100(x) = 100 · x / OFFPOSS_i` (offense) or `/ DEFPOSS_i` (defense).

**Mid-rank percentile and Z.** For any component `x` across the population: `pct(x) = (#players with lower x + 0.5 · #players tied) / N`, and `Z(x) = Φ⁻¹(pct(x))`. Components where lower is better are negated before ranking.

**Final rating.** `Rating = 99 × pct(Score)`, stored as an unrounded `double`; rounded only for display. `Score` is whatever the attribute's section defines. There is **no** non-linear reshaping at this stage. The non-linear (sigmoid-family) curve in doc 01 is the *engine's* attribute→probability link, fit per move against real outcomes in Phase 2.

## Shrinkage: four families, one per kind of statistic

Nothing is hand-picked: every prior is fit by method-of-moments on the real league-wide distribution of that exact statistic.

**S1 — Beta-Binomial, for true proportions** (successes ÷ countable opportunities: FT%, rebound conversion, STL%, FOUL%, blocks per contest). Fit Beta(α, β): `m` = mean of observed rates; `v` = variance of observed rates minus the mean of `p(1-p)/n`; `α+β = m(1-m)/v − 1`; `α = m(α+β)`. Shrunk rate = `(successes + α) / (opportunities + α + β)`. **Build guard:** before fitting, the build asserts `successes ≤ opportunities` for every player and every S1 statistic, and aborts listing the statistic and offenders if not (nothing is clipped).

**S2 — Gamma-Poisson, for counts per unit of exposure** (attempts per 100 possessions, points per possession, deflections per 100). With `r_i = c_i / E_i`: prior mean `m` = mean of `r_i`; `v` = variance of `r_i` minus mean of `m / E_i`; shape `k = m² / v`. Shrunk rate = `(c_i + k) / (E_i + k/m)`.

**S3 — Normal-Normal, for differences from an expected value** (made shots minus expected makes, points-delta vs expected). Per player: observed difference per attempt `d_i` and its sampling variance `s_i²` (stated per attribute). Prior mean 0; `τ² = max(0, Var(d_i) − mean(s_i²))`. Shrunk `d_i* = d_i · τ² / (τ² + s_i²)`. If `τ² = 0` the build logs that the statistic has no detectable true spread and the component is set to 0 for everyone.

**S4 — Poisson-Gamma relative risk, for observed ÷ expected event counts** (turnovers or blocks vs. expected given load/contests). With observed `O_i`, expected `E_i`: `RR_i = O_i / E_i`; prior Gamma(k, k) (mean 1) with `1/k = max(0, Var(RR_i) − mean(1/E_i))`. Shrunk `RR_i* = (O_i + k) / (E_i + k)`.

For variance and delta-style trait statistics (Consistency, Clutch) the analogous Scaled-Inverse-Chi-Squared prior applies; see `04-player-trait-system.md`.

## Expected-value models (the "difficulty adjustment")

**E1 — Shot make model.** For each shot bucket defined below, fit a logistic regression on *all league shots in that bucket* (ShotChartDetail): make ~ one-hot(`ACTION_TYPE`) + `SHOT_DISTANCE` + `SHOT_DISTANCE²` + `|LOC_X|` + one-hot(`SHOT_ZONE_AREA`). **Every E1 model is an L2-penalized (ridge) logistic regression** with an unpenalized intercept and standardized continuous features, with the penalty λ chosen by 5-fold cross-validation (folds split by game) minimizing log-loss over the same 21-value log-spaced grid as the stint ridge; the penalty keeps rare `ACTION_TYPE` levels from producing infinite coefficients. Each shot gets an expected make probability `p̂`. **E1-all** is the same model fit on *every* field-goal attempt (all buckets, threes included, with `SHOT_TYPE` added); it is used only where a shot-difficulty offset is needed for all shots (Stamina). For a player: `d_i = (makes − Σp̂) / n`, `s_i² = Σ p̂(1−p̂) / n²`. (Public shot-chart data has no defender information, so E1 cannot adjust for contest quality; that is the data ceiling stated in doc 11. Threes are the exception: E2.)

**E2 — Defender-distance cell expectation (threes).** From LeagueDashPlayerPtShot with GeneralRange ∈ {Catch and Shoot, Pullups} × CloseDefDistRange ∈ the four closest-defender buckets: league 3P% for each of the 8 cells `q_c = ΣFG3M_c / ΣFG3A_c`. For a player: expected makes `Σ_c FG3A_ic · q_c`; `d_i = (FG3M − expected) / A_i`; `s_i² = Σ_c FG3A_ic · q_c(1−q_c) / A_i²`, with `A_i` the 3PA covered by those cells.

**E3 — Turnover expectation models.** Poisson regressions (maximum likelihood, whole population, exposure as offset) defined in Ball Handle, Passing Accuracy and Offensive IQ below.

**E4 — Zone value `u(z)`.** For each `SHOT_ZONE_BASIC` zone `z`: `u(z) = (2·FG2M_z + 3·FG3M_z) / FGA_z` league-wide, from ShotChartDetail. Expected points per attempt from location alone. **`u_rim`** is the same quantity for all shots with `SHOT_DISTANCE < 6` ft, and `u_other` for all shots at 6 ft or more; these match the "Less Than 6Ft" tracking category used in Defense.

**E5 — Block expectation.** For each contest category `c` (below) the league block rate `b_c = league blocks on shots in category c ÷ league D_FGA in category c`, where blocks come from play-by-play (a missed shot carrying a blocker) classified into category c by the shot's distance and type. A player's expected blocks = `Σ_c D_FGA_ic · b_c`.

## Stint ridge regressions (RAPM family)

Used for Offensive/Defensive RAPM (the IQ regression targets), shot-quality suppression, and rim deterrence. One construction, three different `y`:

- Rows: **stints** (continuous stretches with the same ten players on the floor), reconstructed from play-by-play plus substitutions. Row weight = possessions in the stint.
- Columns: two per player — an *offense* coefficient (+1 when he is on the floor and his team has the ball) and a *defense* coefficient (+1 when he is on the floor and his team is defending); plus an unpenalized intercept.
- Ridge penalty λ chosen by 5-fold cross-validation (folds split by game) over a log-spaced grid, 21 values from 10¹ to 10⁵.
- `y` variants: **Offensive/Defensive RAPM** = points scored by the offense per 100 possessions; **shot-quality** = `Σ u(zone of each FGA) / possessions × 100`; **rim attempts** = offense's FGA with `SHOT_DISTANCE < 6` ft per 100 possessions.
- A player's *defense* coefficient is his effect on the opponent's `y` while he defends (negative = suppresses).

## Shared stat definitions

**Offensive Load and Box Creation** (Ben Taylor / Thinking Basketball; computable from standard box-score data; all terms per 100 of his own on-floor team possessions):

```
3pt proficiency = (2 / (1 + EXP(-3PA)) - 1) * 3P%
Box Creation    = Ast*0.1843 + (Pts+TOV)*0.0969 - 2.3021*(3pt proficiency)
                  + 0.0582*(Ast*(Pts+TOV)*3pt proficiency) - 1.1942
Offensive Load  = ((Ast - 0.38*BoxCreation)*0.75) + FGA + (FTA*0.44) + BoxCreation + TOV
```

**Turnover taxonomy** (from play-by-play turnover types; the build aborts and prints the distinct list if it meets a type not assigned here):
- **Handling turnovers:** Lost Ball (including Out of Bounds – Lost Ball), Traveling, Double Dribble, Discontinued Dribble, Palming.
- **Bad-pass turnovers:** Bad Pass, Out of Bounds – Bad Pass.
- **Decision turnovers:** every other type (offensive fouls, 3-second, shot clock, offensive goaltending, lane/jump-ball violations, and so on).

**Creation possessions** = Synergy Isolation + Synergy PRBallHandler possessions (self-created off the dribble).

**Contest accounting (LeagueDashPtDefend).** Each row gives, for the shots on which the player was the *closest defender*: `A = D_FGA`, `M = D_FGM`, `q = NORMAL_FG_PCT` (the FG% those same shots produce league-wide, i.e. the expectation given who shot and from where), `E = q · A`. Three **disjoint, exhaustive** categories, built from the dashboard's overlapping ones:
- **P3** (perimeter threes) = "3 Pointers".
- **R** (rim) = "Less Than 6Ft".
- **P2** (non-rim twos) = "2 Pointers" minus "Less Than 6Ft" (A, M and E each subtracted).

Points saved per category (positive = good defense): `PS_P3 = 3·(E−M)`, `PS_P2 = 2·(E−M)`, `PS_R = 2·(E−M)`. Per-attempt delta `δ = PS / A`, sampling variance `s² = pts² · q̄(1−q̄) / A` with `q̄ = E/A` (S3). **DIFF%** as databallr/NBA publish it (`PCT_PLUSMINUS = D_FG_PCT − NORMAL_FG_PCT`; negative = good) is the FG%-scale version of the same quantity; we compute from `D_FGM` and `NORMAL_FG_PCT` so its sign can never be misread, and `--smoke` asserts `PCT_PLUSMINUS ≈ D_FG_PCT − NORMAL_FG_PCT`. **DFGA per100** = `A` per100 DEFPOSS (S2), **RIMDFGA per100** is the same for category R.

**Foul cost.** From play-by-play: `SF_i` = shooting fouls committed by player *i*; `f̄` = league free-throw points scored per shooting foul (all free throws awarded on shooting fouls ÷ shooting fouls). **FOUL%** `φ_i = SF_i / (D_FGA_overall + SF_i)` (shooting fouls per contest, S1); `φ̄` = league mean. Foul cost relative to average, per 100: `FC_i = f̄ · (φ_i* − φ̄) · DFGA_overall per100`. It is allocated to a defensive attribute in proportion to that attribute's share of his contests (perimeter attributes: `(A_P3+A_P2)/A_overall`; Rim Protection: `A_R/A_overall`).

**STOP.** `STOP_i` = steals + offensive fouls drawn (play-by-play: offensive foul events with him as the drawer, which includes charges) + blocks recovered (a block whose very next rebound belongs to the blocker's team); STOP per100 DEFPOSS (S2). This is databallr's "directly created defensive stops" built from events we can see.

## Measurables — not rated, pulled directly

- Height, Weight: the roster data. Wingspan: draft combine where available; otherwise `a + b × height`, a regression fit on the real combine players who have both (per `11-phase-1-3-build-and-data-pipeline-plan.md`).

## Rim Scoring

**Shot buckets** (ShotChartDetail `ACTION_TYPE` text, applied in this order, case-insensitive; the build aborts and prints the distinct values if any shot in the Restricted Area or In The Paint (Non-RA) zones is left unclassified and is not a jump shot):

1. contains "Dunk" → starts with "Driving" or "Running" → **DRIVING_DUNK**; otherwise (Cutting, Alley Oop, Putback, Tip, plain Dunk) → **STANDING_DUNK**
2. contains "Layup" or "Finger Roll", and starts with "Driving" or "Running" → **DRIVING_LAYUP**
3. any other shot in zone Restricted Area / In The Paint (Non-RA) whose action contains Layup, Finger Roll, Hook, Floating, Floater, Tip, Putback or Bank → **TOUCH**

| Attribute | Components | Score |
|---|---|---|
| Driving Layup | Efficiency: layup-bucket `d*` (E1, S3). Volume: DRIVING_LAYUP attempts per100 (S2). Contact: `DRIVE_FTA` per100 OFFPOSS (S2; free throws drawn on drives, the part of finishing the shot chart cannot see) | `mean(Z(eff), Z(vol), Z(drive FTA))` |
| Driving Dunk | Single component: DRIVING_DUNK **makes** per100 (S2). Dunk conversion is near-saturated, so a percentage mostly measures how easy a player's dunks were; made dunks at scale already contain the success | `Z(makes per100)` |
| Standing Dunk | Single component: STANDING_DUNK **makes** per100 (S2) — cuts, lobs, putbacks | `Z(makes per100)` |
| Touch | Efficiency: TOUCH-bucket `d*` (E1, S3). Volume: TOUCH attempts per100 (S2). Touch signal: FT%* (S1; soft touch carries over from the line to floaters and hooks) | `mean(Z(eff), Z(vol), Z(FT%*))` |
| Post Scoring | Efficiency: Synergy Postup **PPP** (S2; includes free throws and turnovers). Volume: Postup possessions per100 (S2) | `½ Z(eff) + ½ Z(vol)` |

Cross-check, not an attribute: overall **Rim FG%** (< 6 ft) should be approximately reconstructed by the frequency-weighted DRIVING_LAYUP / DRIVING_DUNK / STANDING_DUNK / TOUCH rim shots; large gaps mean a bucket rule is wrong.

## Shooting

| Attribute | Components | Score |
|---|---|---|
| Three Pointer | Efficiency: `d*` of 3P% vs. the defender-distance × catch-and-shoot/pull-up cell expectation (E2, S3). Volume: 3PA per100 (S2). Touch signal: FT%* (S1; the most stable public sign of shooting touch, which steadies small-sample three-point rates) | `mean(Z(eff), Z(vol), Z(FT%*))` |
| Mid Range | Efficiency: `d*` on SHOT_ZONE_BASIC = "Mid-Range" shots vs. the E1 model (`ACTION_TYPE` already separates pull-ups, step-backs, fadeaways). Volume: Mid-Range attempts per100 (S2). Touch signal: FT%* (S1) | `mean(Z(eff), Z(vol), Z(FT%*))` |
| Free Throw | Single component: FT% (S1, opportunities = FTA). Volume is deliberately excluded: free-throw volume is foul-drawing, which is the Foul/Contact-Seeking tendency. Other shooting stats are not mixed in: the line is the one shot with no defender, so FT% is the cleanest read of that skill | `FT%*` |

## Playmaking

**Ball Handle** — handling security *at the load he carries*, plus the load itself.
- *Security:* handling-turnover count `O_i`. Exposure = dribbles `= TOUCHES × AVG_DRIB_PER_TOUCH`. Expected `E_i = dribbles_i · exp(a + b₁·ln(OffensiveLoad per100) + b₂·CreationPoss per100)` from the league-wide Poisson regression (E3). `RR*` by S4. Component `Z(−RR*)`.
- *Creation efficiency:* points per possession on his Isolation + PRBallHandler possessions (S2; includes free throws and turnovers), i.e. how well the shots he creates turn out.
- *Volume group (equal-weighted inside the group):* creation possessions per100 (S2), Offensive Load per100 (S2) and `DRIVES` per100 (S2). Offensive Load already contains his shots (FGA, FTA), assists and turnovers.
- `Score = ⅓ Z(−RR*) + ⅓ Z(creation PPP*) + ⅓ · mean( Z(creation per100), Z(load per100), Z(drives per100) )`.

**Passing Accuracy** — accuracy given pass risk, plus passing load.
- *Security:* bad-pass turnovers `O_i`. Exposure = `PASSES_MADE`. Expected `E_i = passes_i · exp(a + b·(POTENTIAL_AST / PASSES_MADE))` (E3): a passer whose passes are more often shot-creating is expected to throw more bad ones. `RR*` by S4.
- *Volume group:* `PASSES_MADE` per100 and `AST_ADJ` per100 (S2 each).
- `Score = ½ Z(−RR*) + ½ · mean( Z(passes per100), Z(AST_ADJ per100) )`.

**Vision** — how many scoring chances he creates, and how valuable they are.
- *Volume group (equal-weighted inside):* `POTENTIAL_AST` per100 and `AST_ADJ` per100 (assists + free-throw assists + secondary assists), and `AST_POINTS_CREATED` per100 (points scored off his assists), all from the Passing dashboard, S2 each. Potential assists carry no teammate-shooting luck; `AST_ADJ` credits the pass before the assist.
- *Quality:* for his assists that led to made baskets, the mean zone value `u(zone)` (E4) of the assisted shot (play-by-play assister joined to ShotChartDetail by game + event). `d_i = mean u − league mean u`, `s_i² = σ²_u / n_assists`; S3. Where he gets teammates shots, not whether teammates hit.
- `Score = ½ Z(quality d*) + ½ · mean( Z(potential assists per100), Z(AST_ADJ per100), Z(AST_POINTS_CREATED per100) )`.

**Offensive IQ** — Rule A (below) with target = Offensive RAPM. Components (each a z-scored shrunk statistic):
1. *Shot-choice value:* mean `u(zone)` over his own FGA minus league mean (S3, `s_i² = σ²_u / FGA`).
2. *Decision-turnover avoidance:* decision turnovers vs. expected given Offensive Load per100 (Poisson regression as in E3), `RR*` by S4, negated.
3. *Screen impact:* `SCREEN_ASSISTS` per100 and `SCREEN_AST_PTS` per100 (Hustle Stats, S2 each; two components).
4. *Off-ball action production:* Synergy Cut + OffScreen + Handoff **points** per100 OFFPOSS (S2).
5. *Passing decision value:* Vision's assisted-shot quality `d*` and `AST_ADJ` per100.
6. *Box Creation per100* (Ben Taylor formula above).

Because the weights come from the regression, a component that does not help predict Offensive RAPM simply gets weight 0 and is logged, so adding evidence here costs nothing.

## Defense

The seven rows below that are not rebounding or steals all follow the same logic: opponent points compared with what the same shots are expected to produce, times how many such shots he handles, minus what his fouls cost.

| Attribute | Definition | Score |
|---|---|---|
| Offensive Rebounding | *Efficiency group:* conversion `OREB ÷ (OREB_CHANCES − OREB_CHANCE_DEFER)` (S1; chances he did not defer to a teammate) and ORB% (S1). *Volume group:* `OREB_CHANCES` per100 OFFPOSS, `OFF_LOOSE_BALLS_RECOVERED` per100 and `OFF_BOXOUTS` per100 (S2 each). | `½ mean(Z(conversion), Z(ORB%*)) + ½ mean(Z(chances), Z(off loose balls), Z(off boxouts))` |
| Defensive Rebounding | Same construction with `DREB`, `DREB_CHANCES`, `DREB_CHANCE_DEFER`, DRB%, `DEF_LOOSE_BALLS_RECOVERED` and `DEF_BOXOUTS`, exposure DEFPOSS | `½ mean(Z(conversion), Z(DRB%*)) + ½ mean(Z(chances), Z(def loose balls), Z(def boxouts))` |
| Steals | *Rate:* STL% = steals ÷ opponent possessions while on floor (S1). *Hands:* deflections per100 DEFPOSS (S2). Both are rates of active-hands plays, so they are equal-weighted | `½ Z(STL%*) + ½ Z(deflections per100*)` |
| Shot Blocking | *Skill:* blocks over expected blocks given the mix of shots he contests, `RR_BLK = BLK ÷ E5` with S4. *Volume:* BLK% = blocks ÷ opponent 2-point attempts while on floor (S1) and BLK per100 DEFPOSS (S2). All come from the same play-by-play block events | `½ Z(RR_BLK*) + ½ mean(Z(BLK%*), Z(BLK per100*))` |
| On-Ball Defense | **Net perimeter points saved per 100** over disjoint categories P3 and P2: `[ A_P3*·δ_P3* + A_P2*·δ_P2* ] − FC_perimeter`, where each `A*` is that category's D_FGA per100 DEFPOSS (S2) and each `δ*` its points-saved-per-attempt delta (S3). This contains DFGA/100, DIFF% and FOUL% in one number. | `pct( net points saved per100 )` |
| Post Defense | Synergy defensive Postup: PPP allowed (S2) and possessions per100 DEFPOSS (S2). | `pct( poss per100* · (league PPP − PPP*) )` |
| Rim Protection | **Net rim points saved per 100 = contest value + deterrence value − foul cost.** *Contest:* `A_R*·δ_R*` (RIMDFGA per100 times the rim DIFF% in points, S2 and S3). *Deterrence:* the rim-attempts stint ridge gives his defense coefficient `γ_i` = change in opponent FGA from < 6 ft per 100 possessions while he defends; `deterrence_i = −γ_i · (u_rim − u_other)`, the points an attempt is worth over the shot it is replaced by. Ridge already shrinks `γ_i`, so no second shrinkage. *Foul cost:* `FC_i · A_R/A_overall`. | `pct( contest + deterrence − foul cost )` |
| Off-Ball Defense | Rule B (equal-weighted z-scores): **help contests** = the residual of `CONTESTED_SHOTS` per100 DEFPOSS regressed (OLS across the population) on `D_FGA`(Overall) per100 DEFPOSS, i.e. contests beyond what his own closest-defender volume predicts, z-scored (it may be negative, which is fine for a z-score; no subtraction of counts is ever treated as a proportion); BLK per100 DEFPOSS (S2); deflections per100 DEFPOSS (S2; also used in Steals); charges drawn per100 DEFPOSS (Hustle Stats, S2). The `HELP_*` matchup columns were confirmed all-zero in the real data and are not used anywhere | `mean of the 4 Z` |
| Defensive IQ | Rule A with target = Defensive RAPM. Components: shot-quality suppression (stint ridge, shot-quality variant, defense coefficient, negated); **STOP per100** (S2); non-shooting defensive fouls per100 DEFPOSS (S2, negated; shooting fouls are already priced in FOUL%); contested shots per100 DEFPOSS (Hustle Stats, S2); deflections, charges drawn and total loose balls recovered per100 DEFPOSS (S2 each); BLK% (S1); rim DIFF% in points (`δ_R*`). Rule A keeps whichever predict Defensive RAPM | Rule A composite |

**Why Rim Protection is built this way:** the best rim protectors change what the offense *attempts*. A player who is never beaten because opponents stop going to the rim contests nothing and blocks nothing, and block rate or contested FG% alone would miss him entirely. The deterrence term measures the attempts that disappeared (adjusted for teammates and opponents by the ridge); the contest term values what happens on the attempts that still occur, using the rim DIFF% on what he contested.

**How Shot Blocking and Rim Protection coexist:** the engine resolves a contest in two steps. First a block is rolled from Shot Blocking; if there is no block, the miss probability comes from the contest ratings. Rim Protection's contested-FG% term includes blocked shots as misses (public data does not split them), so Phase 2 fits the engine's Rim Protection curve to FG% on *unblocked* contests using its own simulated blocks. The overlap is listed under "Known overlaps".

## Physicals

Athletic tests (DraftCombineStats): `THREE_QUARTER_SPRINT`, `LANE_AGILITY_TIME`, `MODIFIED_LANE_AGILITY_TIME`, `MAX_VERTICAL_LEAP`, `STANDING_VERTICAL_LEAP`, `BENCH_PRESS`. **Test value (final)** = his own combine result when he has one; otherwise the **predicted** value from a ridge regression (λ by 5-fold CV) fit on players who do have that test, using **body and demographic features only**: height, weight, wingspan, age, published position (one-hot). Tracking variables are deliberately *not* used in the prediction, because the prediction exists to fill a missing test and the tracking residuals below are separate evidence.

**Tracking residuals.** `AVG_SPEED_OFF` and `AVG_SPEED_DEF` (SpeedDistance) are role- and team-driven, so each is replaced by its residual from an OLS on published position (one-hot), age, and team pace (possessions per 48). Residuals are then z-scored.

All test values are z-scored across the population, time-based tests negated.

| Attribute | Score (Rule B: equal-weighted mean of the listed z-scores) |
|---|---|
| Speed | `−z(THREE_QUARTER_SPRINT final)`, `z(AVG_SPEED_OFF residual)` |
| Acceleration | `−z(THREE_QUARTER_SPRINT final)`, `−z(MODIFIED_LANE_AGILITY_TIME final)`, `z(STANDING_VERTICAL_LEAP final)` (lower-body power predicts sprint acceleration), `z(DRIVES per100 OFFPOSS residual)` (revealed first step: the residual from the same position/age/team-pace OLS used for speed; Drives dashboard) |
| Lateral Quickness | `−z(LANE_AGILITY_TIME final)`, `−z(MODIFIED_LANE_AGILITY_TIME final)`, `z(AVG_SPEED_DEF residual)` |
| Vertical | `z(MAX_VERTICAL_LEAP final)`, `z(STANDING_VERTICAL_LEAP final)`, `z(above-rim finishing residual)` where above-rim finishing = made DRIVING_DUNK + STANDING_DUNK per100 OFFPOSS (S2), residualized on height and published position |
| Strength | `z(WEIGHT)`, `z(BENCH_PRESS final)`. No in-game stat is used here: every public one (rebound contests, post results, screens) mixes strength with role and skill |
| Stamina | `Z(β*)`, `Z(stint length*)` and `z(distance covered per 48 minutes residual)`, equal-weighted; the distance is `DIST_MILES_OFF + DIST_MILES_DEF` per 48 minutes, residualized like the speeds (sustained movement is direct evidence of endurance). `β_i` = per-player logistic-regression coefficient on *minutes continuously on floor at the time of the shot*, with the E1-all logit of each shot as offset; standard error from the fit; S3 toward the league mean `β̄` (prior mean estimated, not 0). `stint length` = his mean continuous minutes per stint, S3 with sampling variance = pooled within-player stint variance ÷ number of stints |

Acceleration is the one where the evidence is thinnest and the first step matters most in the game, so it combines two combine tests, the power test, and an in-game revealed measure rather than relying on a single trial. Its in-game component (drive frequency) also reflects role and skill, which is accepted under the reuse rule and checked in Phase 3.

These are the weakest-signal attributes by nature: public tracking has no true top-speed, acceleration or strength test, and combine results are from draft day. A player with no combine result gets a mostly position-and-size-driven prediction for the test part; the tracking residual (speed, lateral) and the stamina measures are the parts that vary within a position. Where a statistic has no detectable true spread (Stamina's β, S3 with τ² = 0) the build logs it and the component drops out rather than adding noise.

## Blending weights: fit from data, never hand-picked

**Rule A — regression-fit weights, when an independent real target exists.** Z-score each component, then fit non-negative least squares of the target on the component z-scores; rescale the coefficients to sum to 1. Refit every time the pipeline runs. A component whose coefficient comes out 0 drops out and is logged.
- Offensive IQ → target **Offensive RAPM**; Defensive IQ → target **Defensive RAPM**.

**Rule B — equal-weighted mean of z-scores, when no independent target exists.** Steals, Shot Blocking, Off-Ball Defense, the Physicals, and the equal-weighted groups inside the composites above. The Hustle trait in `04-player-trait-system.md` reuses it too.

**Efficiency/volume composites** use equal weight between "how well" and "how much": no independent real outcome says how much one should outweigh the other, so the neutral default applies and Phase 3 validates it.

**Rebounding fallback (deterministic).** If `--smoke` shows the rebound-chance columns missing, Offensive/Defensive Rebounding use ORB% / DRB% (S1) alone and the build records which rule was used.

## Considered and not used (and why)

| Stat | Reason |
|---|---|
| `HELP_*` matchup columns | Confirmed 0 in all 151,960 real rows; help defense is read from contests beyond the closest-defender volume instead |
| Ball Security, Shot Selection | Removed; covered inside Ball Handle / Passing Accuracy / Offensive IQ |
| Gravity, ball dominance, true top speed, true contest distance, matchup-level assignment | Not public; parked, not approximated |
| And-1 rate, shooting fouls drawn | Cannot be attributed to a shot bucket from public data; foul drawing is the Foul/Contact-Seeking tendency |
| Assist-to-pass conversion (`AST_TO_PASS_PCT`) | Depends on teammates' shooting luck |
| Drive efficiency | Finishing is already in Driving Layup/Dunk (drive *frequency* is used in Acceleration) |
| Contested-rebound share, post results, screens as strength | Mix strength with role and skill; Strength stays on weight and bench press |

## Known overlaps (deliberate, to be validated in Phase 3)

- Efficiency + volume inside ratings and the matching tendency (see top).
- Shot Blocking vs. Rim Protection contest term (blocks are misses).
- STOP in Defensive IQ vs. Steals / Shot Blocking (STOP contains steals and recovered blocks); Rule A decides its weight.
- Deflections feed Steals and Off-Ball Defense; charges drawn feed Off-Ball Defense and STOP; contested shots feed Defensive IQ and (as `D_FGA`) the points-saved attributes.
- Free Throw % feeds Free Throw, Touch, Three Pointer and Mid Range. AST_ADJ feeds Passing Accuracy and Vision; assisted-shot quality feeds Vision and Offensive IQ. Drives feed Ball Handle, Acceleration and Driving Layup (via drive FTA). Deflections and charges feed several defensive attributes; BLK% feeds Shot Blocking and Defensive IQ.
- Physicals: the sprint feeds Speed and Acceleration; modified lane agility feeds Acceleration and Lateral Quickness; standing vertical feeds Vertical and Acceleration; drives per100 feeds Acceleration and the Drive tendency.

## Additional real cross-check metrics (Phase 3 calibration)

- **RAPM** (self-computed): standing validation of the IQ attributes.
- **DPM** (DARKO's Daily Plus-Minus): independent all-in-one impact model.
- **Pts Saved/100, D-SQI, DIFF%, STOP%, BLK%** (databallr): published versions of the ideas used above, for comparing our own computed values.
- **Six-Factor decomposition**: lineup-adjusted splits, a parallel check across several attributes.

## Data requirements checklist (for `gather.py --smoke`)

"Documented" = confirmed in the nba_api endpoint documentation; "smoke" = standard on stats.nba.com but not confirmable from the docs, so `--smoke` must verify before the long run.

| Source | Parameters | Columns needed | Used by | Status |
|---|---|---|---|---|
| ShotChartDetail (per player) | ContextMeasure FGA, 2025-26 Regular Season | `GAME_ID, GAME_EVENT_ID, ACTION_TYPE, SHOT_ZONE_BASIC, SHOT_ZONE_AREA, SHOT_DISTANCE, LOC_X, LOC_Y, SHOT_MADE_FLAG, SHOT_TYPE` | Rim Scoring, Mid Range, E1, E4, ridge, Vision | smoke |
| LeagueDashPlayerPtShot | GeneralRange {Catch and Shoot, Pullups} × CloseDefDistRange (4 buckets) | `FG3M, FG3A, FGA, FGM` | Three Pointer | columns documented; parameter strings: smoke |
| LeagueDashPtDefend | DefenseCategory {Overall, 3 Pointers, 2 Pointers, Less Than 6Ft} | `D_FGM, D_FGA, D_FG_PCT, NORMAL_FG_PCT, PCT_PLUSMINUS, FREQ` | On-Ball, Rim Protection, Shot Blocking, foul cost | documented. Smoke asserts: `PCT_PLUSMINUS ≈ D_FG_PCT − NORMAL_FG_PCT`; "3 Pointers" + "2 Pointers" ≈ "Overall" within 1%; "2 Pointers" D_FGA ≥ "Less Than 6Ft" D_FGA; league ΣD_FGA ≈ league FGA (blocked shots included) |
| SynergyPlayTypes (player, offense and defense) | Isolation, PRBallHandler, Postup, Cut, OffScreen, Handoff | `POSS, PPP, PTS, FGA, TOV_POSS_PCT` | Post Scoring/Defense, Ball Handle, Offensive IQ | documented for team form; player form: smoke |
| LeagueDashPtStats | Possessions; Passing; Rebounding; Drives; SpeedDistance | Drives: `DRIVES, DRIVE_FTA`; Possessions: `TOUCHES, AVG_DRIB_PER_TOUCH`; Passing: `PASSES_MADE, POTENTIAL_AST, AST_ADJ, FT_AST, SECONDARY_AST, AST_POINTS_CREATED`; Rebounding: `OREB, DREB, OREB_CHANCES, DREB_CHANCES, OREB_CHANCE_DEFER, DREB_CHANCE_DEFER`; SpeedDistance: `AVG_SPEED_OFF, AVG_SPEED_DEF, DIST_MILES_OFF, DIST_MILES_DEF` | Ball Handle, Passing, Vision, Rebounding, Speed, Lateral | SpeedDistance documented; others: smoke |
| LeagueHustleStatsPlayer | — | `CONTESTED_SHOTS, DEFLECTIONS, CHARGES_DRAWN, SCREEN_ASSISTS, SCREEN_AST_PTS, OFF_LOOSE_BALLS_RECOVERED, DEF_LOOSE_BALLS_RECOVERED, OFF_BOXOUTS, DEF_BOXOUTS` | Steals, Off-Ball, Rebounding, Offensive IQ, Defensive IQ | smoke |
| DraftCombineStats | — | `THREE_QUARTER_SPRINT, LANE_AGILITY_TIME, MODIFIED_LANE_AGILITY_TIME, MAX_VERTICAL_LEAP, STANDING_VERTICAL_LEAP, BENCH_PRESS, WINGSPAN, HEIGHT_WO_SHOES, WEIGHT` | Physicals, Measurables | documented |
| **Play-by-play** (primary: `cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{GAME_ID}.json`; backup: nba_api `PlayByPlayV3`; archive: `shufinskiy/nba_data`) | every game | action type and subtype, `personId`, assist / block / steal / foul-drawn person ids, shot result and distance, free-throw series, substitutions, clock, period | turnovers, assists, blocks, STOP, shooting fouls, `f̄`, stints, ridge | smoke. **`PlayByPlayV2` is dead in nba_api 1.11.4 and `PlayByPlayV3` has no assister ids, so neither is the primary source.** |
| Box score (starters, minutes), player game logs | every game | starters, minutes, games played | exposure, Stamina | existing pipeline |

## Sources
- [databallr Stats Glossary](https://databallr.com/stats/glossary) — Pts Saved/100, D-SQI, DFGA, DIFF%, FOUL%, RIMDFGA, STOP%, BLK%, Rim AST, RAPM; the sTOV% and PASSTOV definitions that motivated the Ball Handle and Passing Accuracy design
- [DARKO (darko.app)](https://darko.app) — DPM
- [Thinking Basketball — "Offensive Load and Adjusted TOV%"](https://thinkingbasketball.net/2017/10/16/offensive-load-and-adjusted-tov/) — Offensive Load (Ben Taylor)
- [Sal's Substack — "Intro to Ben Taylor's Passing Metrics"](https://salnba.substack.com/p/intro-to-ben-taylors-passing-metrics) — Box Creation formula
- [nba_api endpoint documentation](https://github.com/swar/nba_api/tree/master/docs/nba_api/stats/endpoints) — LeagueDashPtDefend, LeagueDashPlayerPtShot, SynergyPlayTypes, LeagueSeasonMatchups, DraftCombineStats columns
- David Robinson, *Introduction to Empirical Bayes: Examples from Baseball Statistics* — Beta-Binomial method-of-moments shrinkage
