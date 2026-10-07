# Phase 1 documentation gaps

Every field the docs fully specify is implemented. The fields below are not, because doing so
would mean choosing a formula, input or threshold the docs don't give. Under the project's hard
rule that choice is yours, not the implementer's. Each gap lists the doc and section, what's
missing, and a **proposed resolution**. The proposals are not implemented: approve, change or
reject each one, and the build picks it up without another network pass (the gather step already
pulls every input the proposals need, except where noted).

`build.py` writes each field's status (`derived`, `partial`, `failed`, `blocked`) and gap ids into the
`derivation_status` table, and `dotnet run --project tools/NbaGm.Phase1Check` prints the same list.

## Blocking gaps (G)

### G1. Percentile → 0–99 curve is undefined. Blocks every attribute's final rating.
- **Docs:** 02 "four-step pipeline" step 4; 01 "Scale decision" §2 and "Still open" bullet 2.
- **Problem:** Doc 02 maps a league percentile through "the locked non-linear curve from the
  attribute doc" and says its parameters are "fit against the real percentile distribution". But a
  percentile is uniform on (0, 1) by construction, so there is nothing to fit. Steepness and
  inflection would be hand-picked. Doc 01 §2 also describes that curve as the
  **attribute → probability** mapping used in move resolution (Phase 2), which is a different
  function from **stat percentile → rating**. The two docs disagree on what the curve is.
- **Proposed:** Keep the sigmoid where doc 01 puts it (Phase 2, attribute → probability), and make
  Phase 1's mapping parameter-free: `rating = 99 × percentile`. That needs one sentence in doc 02.
  Alternative: state the target display distribution explicitly (e.g. "the 50th percentile maps to
  X, the 99th to Y"), which pins the curve's parameters.

### G2. No rule for assigning role tags.
- **Docs:** 06 "Player roles" / "Multi-role tagging"; used by 04 Consistency ("same primary role
  tag"), 02 Vision ("adjusted against the player's role") and 02 step 4 ("a few attributes (noted
  below)" compare within role, but none are noted).
- **Problem:** Doc 06 lists the 13 + 7 roles, but nothing says how a player's primary and secondary
  role are computed from real stats. BBall Index's classifier is proprietary.
- **Proposed:** Specify a rule per role on the Synergy play-type and tracking frequencies already
  pulled (e.g. primary offensive role = the role whose defining frequency is highest relative to
  the league), and say which attributes, if any, use same-role percentiles.

### G3. How the difficulty adjustment works is unspecified.
- **Docs:** 02 pipeline step 3, plus the Driving Layup, Touch, Three Pointer, Mid Range and
  On-Ball Defense rows.
- **Problem:** "Compared against league expected FG% for that shot type" doesn't say whether the
  adjusted value is a difference (FG% − expected) or a ratio (FG% / expected), or whether shrinkage
  happens before or after the adjustment.
- **Proposed:** Shrink makes/attempts per bucket with Beta-Binomial, then
  `adjusted = Σ_bucket share × (shrunk FG% − league FG% in that bucket)`, using the player's own
  attempt shares.

### G4. Recombining the Three Pointer and Mid Range splits.
- **Docs:** 02 "Shooting" table and "Attempt-mix weighting" paragraph.
- **Problems:**
  1. The table weights the C&S/pull-up × defender-distance splits "by the player's actual attempt
     mix", but the next paragraph defines that mix as zone rates (3PR, rim rate, mid rate), which
     can't weight splits inside a single zone.
  2. "Catch and Shoot" and "Pullups" together don't cover every attempt; stats.nba.com's other
     general range ("Less Than 10 ft") and unclassified attempts fall outside both.
  3. stats.nba.com has no defender-distance split for **mid-range** specifically. The closest real
     filter is "2PT, shot distance ≥ 10 ft", which isn't the Mid-Range zone used in doc 03.
- **Proposed:** Splits = {C&S, pull-up, other} × 4 defender-distance buckets, weighted by the
  player's attempt share in each split. Mid Range uses the 2PT ≥ 10 ft filter, explicitly named as
  the source.

### G5. One attribute, several components, no rule for combining them.
- **Docs:** 02 rows for Post Scoring (PPP + FG%), Rim Protection (rim FG% allowed + block rate),
  On-Ball Defense (several overlapping distance categories: < 6 ft, < 10 ft, > 15 ft, 2PT, 3PT) and
  Vision (quantity layer + Rim AST Share).
- **Problem:** 02's two blending rules (A: regression, B: equal-weight z) are stated only for
  Offensive IQ, Defensive IQ, Off-Ball Defense and Strength.
- **Proposed:** Apply Rule B (equal-weight z-scores of the shrunk components) to all four. For
  On-Ball Defense, use the non-overlapping categories 3PT and 2PT.

### G6. Standing Dunk has no defined numerator or denominator.
- **Doc:** 02 Rim Scoring table.
- **Problem:** "Assisted-dunk rate off cuts" with "opportunity = assisted-dunk-eligible looks":
  no public stat counts eligible looks.
- **Proposed:** Makes ÷ attempts on non-driving dunk shot types (shot-chart action types containing
  "Dunk" but not "Driving"; putbacks included or excluded, your call).

### G7. Ball Handle (sTOV%) is under-defined.
- **Doc:** 02 Playmaking table.
- **Problem:** Which play-by-play turnover types are "scoring" turnovers isn't listed (the text
  names travels, discontinued dribble, offensive fouls and mid-drive strips, but the play-by-play
  has about 25 subtypes, e.g. Lost Ball, Step Out of Bounds, Palming). "Opportunity = scoring
  attempts" isn't defined either (FGA? FGA + 0.44·FTA + sTOV?).
- **Proposed:** List the counted subtypes explicitly (`Traveling`, `Discontinued Dribble`,
  `Offensive Foul`, `Lost Ball`, `Double Dribble`, `Palming`, `Step Out of Bounds`), and set
  opportunities = FGA + 0.44·FTA + scoring turnovers.

### G8. Vision's quantity formula.
- **Doc:** 02 Playmaking table.
- **Problem:** "Potential assists relative to actual assists, adjusted against the player's role":
  the direction (potential/actual vs actual/potential), the role adjustment and the shrinkage family
  are all unstated.

### G9. Shot Selection formula.
- **Doc:** 02 Playmaking table.
- **Problem:** "Location/clock-state-implied expected value of the shot mix vs league average by
  zone" doesn't define the expected-value formula, how shot-clock state enters, or how (or whether)
  it's shrunk. The doc itself calls it an "approximation".
- **Proposed:** `xeFG = Σ_zone (player zone share) × (league eFG% in zone)`, using the 7 shot-location
  zones, compared to league xeFG. Drop the clock-state term, or specify it.

### G10. Offensive IQ and Defensive IQ components.
- **Doc:** 02 "Blending weights" Rule A.
- **Problem:**
  - Offensive IQ's components are given only as an "e.g." list.
  - Defensive IQ lists no components at all.
  - RAPM (the regression target) needs a regularization strength that isn't specified.
- **Proposed:** Fix the exact component lists. Choose the RAPM ridge penalty by cross-validation on
  the season's stints.

### G11. D-SQI, the Off-Ball Defense regression target, has no access path.
- **Docs:** 02 "Blending weights" Rule A; 11 "Data gathering" (sources are stats.nba.com,
  balldontlie and Kaggle).
- **Problem:** D-SQI is a databallr metric. Doc 11 names no way to get it, and it isn't derivable
  from the pulled data.
- **Proposed:** Either add databallr as a named source (export or scrape, run locally) or switch
  Off-Ball Defense to Rule B over deflection and loose-ball rates.

### G12. Strength components have no public source.
- **Doc:** 02 "Blending weights" Rule B.
- **Problem:** "Post-up PPP under contact" and "free-throws-drawn-on-contact rate" aren't published
  anywhere (contact isn't tracked). "Contested-offensive-rebound rate" exists (`OREB_CONTEST`,
  already pulled).
- **Proposed:** Components = post-up PPP (Synergy), FTA/FGA on post-ups and drives
  (`DRIVE_FTA`/`DRIVE_FGA`), and OREB_CONTEST/OREB.

### G13. Speed and Acceleration share one input.
- **Doc:** 02 Physicals table.
- **Problem:** Both rows cite "average speed and distance traveled". The doc doesn't say which
  column feeds which attribute, or whether to shrink and how.
- **Proposed:** Speed = `AVG_SPEED_OFF`. Acceleration needs a separate real signal: public tracking
  has none, so it would fall back to the combine three-quarter sprint (same coverage problem as G14).

### G14. Lateral Quickness's fallback doesn't exist.
- **Docs:** 02 Physicals table vs 03 "Parked".
- **Problem:** The fallback for non-combine players is "in-game closeout/screen-navigation
  tracking", which doc 03 itself says isn't public. There's also no rule for putting combine
  seconds and a fallback stat on one scale. Note that combine data is a pre-draft measurement, so
  for veterans it's years old.
- **Proposed:** Specify the fallback stat, or use combine-only with regression imputation from
  height and weight (same method as wingspan).

### G15. Vertical's fallback is undefined.
- **Doc:** 02 Physicals table.
- **Problem:** "Dunk/contested-rebound rate" has no formula, and there's no rule for putting combine
  vertical and the fallback on one scale.

### G16. Stamina formula.
- **Doc:** 02 Physicals table.
- **Problem:** "Performance decline across back-to-backs and late minutes" doesn't say which
  performance stat, which comparison, or what shrinkage. Game logs and quarter splits are already
  pulled.

### G17. Durability: games missed vs games scheduled.
- **Docs:** 04 Durability; 11 names balldontlie/Kaggle as the injury source.
- **Problems:**
  1. "Games scheduled" is undefined for traded, waived, two-way and mid-season signings.
  2. It's unclear whether non-injury absences count (DNP-coach's decision, suspension, G League
     assignment, rest).
  3. balldontlie's injury endpoint covers current injuries only, not history, and no Kaggle dataset
     is named.
- **Proposed:** Scheduled = team games while on that team's roster. Missed = scheduled − games
  played, counting all absences (no injury source needed). This uses the team and player game logs
  already pulled for 2023-24 to 2025-26. If only injury absences should count, name the dataset.

### G18. Consistency: variance of which stat?
- **Doc:** 04 Consistency.
- **Problem:** "Game-to-game statistical variance" doesn't name the stat (points? game score? per
  36?). It also depends on G2 for the role grouping.
- **Proposed:** Per-game Game Score per 36 minutes. Scaled-Inv-χ² shrinkage within the primary role.

### G19. Clutch: stat and shrinkage.
- **Doc:** 04 Clutch and "Minimum sample handling".
- **Problems:**
  1. The stat is given as "e.g. true shooting % swing".
  2. The doc says to shrink the self-delta with an Inverse-Gamma prior. That is a prior on a
     variance, but the delta is a difference of means and can be negative. The shrinkage step for
     the delta itself is undefined.
- **Proposed:** Δ = clutch TS% − non-clutch TS%. Shrink Δ toward the league mean delta with a
  normal–normal model, whose between-player variance is fit by method of moments (the Inverse-Gamma
  prior would then govern only the variance term).

### G20. Positions PG–C have no source.
- **Doc:** 11 "Matchups: every Player gets a Position (PG-C)".
- **Problem:** stats.nba.com and balldontlie publish only G/F/C and hyphenated combos.
- **Proposed:** Name a source (e.g. Basketball-Reference play-by-play position estimates), or derive
  position from a real rule (e.g. height rank within the listed G/F/C group).

### G21. No salary source for the Contract stub.
- **Doc:** 11 "Contract: minimal stub".
- **Problem:** No doc names a salary source. stats.nba.com doesn't publish salaries.
- **Not part of Phase 1's done definition.** The model has the stub; the table is empty until a
  source is named.

### G22. Help Defense Aggressiveness: its source column is empty.
- **Doc:** 03 Defensive approach, Help Defense Aggressiveness (`HELP_FGA ÷ (MATCHUP_FGA + HELP_FGA)`).
- **Found in the real 2025-26 data:** stats.nba.com still publishes the `HELP_FGA`, `HELP_FGM`,
  `HELP_BLK` and `HELP_FG_PERC` columns, but they are 0 in all 151,960 season-matchup rows. Every
  other column in that table is filled. The tendency has no real data as specified, so the
  build marks it failed.
- **Proposed:** shots he defended as the closest defender that weren't taken by his own matchup:
  `(D_FGA − MATCHUP_FGA) ÷ D_FGA`, where `D_FGA` comes from the defender dashboard (Overall).
  This can dip below 0 when matchup tracking credits him with more shots than closest-defender
  tracking does, so it would also need a rule for that (e.g. use `max(0, …)`, or a different
  proxy). Both inputs are already downloaded.

### G23. Pass-First vs Score-First isn't a proportion in the real data.
- **Doc:** 03 On-ball creation, Pass-First vs Score-First (`Passes Made ÷ Touches`).
- **Found in the real 2025-26 data:** 6 players have more passes than touches in the NBA's own
  tracking, and not only tiny samples: Nicolas Batum has 1,409 passes on 1,210 touches, Royce
  O'Neale 3,266 on 3,154, Gary Harris 585 on 568. Most likely inbound passes count as passes but
  not as touches. Beta-Binomial needs successes ≤ opportunities, so the build marks it failed.
- **Proposed:** the pass share of on-ball decisions,
  `Passes Made ÷ (Passes Made + FGA + turnovers)`. It's bounded by construction, and every input is
  already downloaded.

## Implemented as written, but needs your confirmation (F)

These are computed exactly as the docs say. Each produces a result that looks unintended.

- **F1. Foul/Contact-Seeking (03):** FTA ÷ FGA isn't a proportion (FTA can exceed FGA, e.g. low-usage
  bigs), so Beta-Binomial can't apply. If any real player has FTA > FGA, the build marks this
  tendency **failed** (NULL for everyone) rather than clipping it. **Confirmed in the real
  2025-26 data:** Dwight Powell (112 FTA on 101 FGA over 63 games), Alex Antetokounmpo and Grant
  Nelson. Proposed fix: free-throw trips ÷ (FGA + free-throw trips), i.e. how often a shooting
  chance ends at the line. Trips (each "1 of n" free throw) come from the play-by-play already
  downloaded. A simpler alternative is FTA ÷ (FGA + FTA).
- **F2. Defensive Foul Aggression (03):** "personal fouls" (box score PF) includes offensive fouls.
  Defensive-only fouls would come from the play-by-play.
- **F3. Box-Out vs Leak-Out (03):** the denominator as written ("opponent FGA + FTA ending in a
  miss") includes *made* field goals, and the numerator `BOX_OUTS` includes offensive box-outs. The
  likely intent is `DEF_BOXOUTS ÷ (opponent missed FGA + missed final FT)`; both inputs are already
  pulled.
- **F4. Hustle (04):** the components are raw, unshrunk rates. So a player with a few minutes can
  land in "Relentless" or "Lazy" from one event, which contradicts doc 04's own "thin samples can't
  produce an extreme tier". Players with zero minutes get no value (0 ÷ 0). Proposed: use each
  component's Beta-Binomial-shrunk rate, the same mechanism as the matching tendencies.
  **Confirmed in the real 2025-26 data:** Brandon Clarke (about 20 minutes played) comes out at
  z = +5.1, "Relentless", and Chris Mañon (46 minutes) at z = +4.8.

- **F5. Streaky (04):** the shot log contains field goals only, so free throws aren't in the
  sequence. A sequence with all makes or all misses has run count = expectation and zero variance;
  its z is defined as 0 (no claim).
- **F6. Driving Dunk (02):** "dunks off live-dribble drives" is read as shot-chart action types
  containing both "Driving" and "Dunk".
- **F7. Ball Security (02):** Ben Taylor's Offensive Load can be ≤ 0 for players with almost no
  offensive involvement. That makes the Gamma-Poisson exposure non-positive, so those players are
  treated as zero exposure (they get the prior mean).

## Observation from the real data (needs your view, not a bug)

- **O1. Shrinkage is weak for some tendencies, by the docs' own method.** The Beta prior's
  strength (α + β, roughly "how many league-average attempts each player starts with") comes out
  of the real data. Where players genuinely differ a lot, it's small:
  - Catch-and-Shoot vs Pull-Up: 3.5
  - Pick-and-Roll Usage: 4.1
  - Post-Up Frequency: 4.3
  - Three-Point Attempt Rate: 4.4
  - Rim Attempt Rate: 5.3
  - Isolation Frequency: 7.2

  So a 12-possession player who isolated every time ends at 0.64, and a 15-possession post-up
  player at 0.78. That's the method working as doc 02 specifies (it shrinks hard only when
  players are mostly alike), but it contradicts doc 02's own example that tiny samples are
  "shrunk almost all the way" to the average. If that's unwanted, the docs need a different rule
  (e.g. fitting the prior on players above a volume floor, which is itself a hand-picked
  number). Otherwise it stays as is.

## Doc inconsistencies (wording, not blocking)

- Doc 11 "Resolved ambiguities" still lists *Over vs. Under* as an either/or pair, and doc 06
  still names *Closeout Aggressiveness* as a live tendency. Both are parked in docs 01 and 03.

## Mechanical readings I made (flag any you disagree with)

1. **Gamma prior form:** doc 02's formula `(points + k) / (possessions + k/θ)` is a valid posterior
   mean only if θ is the prior *mean* (rate = k/θ), so that's how it's fit.
2. **On-floor counts and possessions:** "while on the floor" counts come from walking the
   play-by-play in order. Q1 starters come from the box score. Later quarters' starters come from
   rotation data when stats.nba.com serves it (it fails for most games), otherwise from the first
   players seen acting in the quarter. Incoming substitutes are matched by name, since the
   play-by-play gives only the outgoing player's ID. Events whose lineup can't be pinned to five
   players are skipped rather than guessed. The build prints the share skipped and checks every
   player's reconstructed minutes against official box-score minutes. Possessions use the
   standard estimate FGA − OREB + TOV + 0.44·FTA applied to on-floor counts.
3. **Rebounds:** ORB% and DRB% denominators count player rebounds only (team rebounds excluded),
   matching the box-score convention. Numerators are official box-score totals.
4. **Priors and percentiles:** priors are fit on players with any opportunities, unweighted, with
   population variance. Percentiles are mid-rank (ties averaged) over everyone who played plus
   everyone rostered.
5. **Play-type denominator:** "total offensive possessions used" = the sum of a player's Synergy
   possessions across all 11 offensive play types.
6. **Shot clock:** "≤ 7 seconds" = the `7-4 Late` and `4-0 Very Late` buckets, over all FGA
   (`ShotClock Off` attempts stay in the denominator).
7. **Wingspan regression:** fit on rostered players who have both a combine wingspan and a listed
   height, so the fitted and applied height are the same measure. A player's latest combine
   measurement is used.
8. **Scope of stats:** season stats cover the full regular season across teams. Starters and
   rotation use games started and minutes with the player's final team.
9. **Season type:** regular season only.
