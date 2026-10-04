
# Team Tactics & Coaching System

## Core model: two layers, not one blended system

A coach's system does not directly edit a player's personal tendency values. Instead:

- **Layer 1 (coach/team level):** decides which sets/actions get called, how often, and who gets put into them (role assignment — primary ball-handler, roll man, designated shooter, etc.). This shapes the *menu of situations* a player encounters.
- **Layer 2 (player level):** once a player is actually in a given situation (ball in hand in a pick-and-roll, open for a catch-and-shoot three), their own personal tendencies and attributes govern what they actually do. Unchanged by coaching — this is pure individual identity.

The coach shapes opportunity and frequency; the player's own nature still governs the in-moment decision. Neither layer overrides the other.

This applies symmetrically to defense: a scheme (switch everything, drop coverage, full-court press, pack the paint) changes how often a given defensive response (e.g. "Navigate a Screen: Switch" vs. "Hedge/Show") gets called as the team default, while the individual defender's own tendencies (Gamble-for-Steals, Help Aggressiveness, Closeout Aggressiveness) still govern how they execute within that structure.

## Conflict between system and player tendency is a deliberate, desired feature

If a coach wants a system built around high three-point volume but a specific player has a naturally low Three-Point Attempt Rate tendency, the system creates more open three-point looks for him — but he still passes up more of them than a "green light" shooter would, because his own tendency governs the choice in the moment. The team's actual output is a product of both the system's design and the roster's real tendencies. A great system with the wrong personnel genuinely underperforms its design. This friction should exist, not be smoothed away — it mirrors how real coach/player fit actually plays out.

## Why the coach doesn't get direct override power

The coach controls opportunity and role (how often a player is put in a situation, whether plays get run for him) but not the in-the-moment decision itself. This deliberately avoids needing a "coachability" attribute/trait — which was already explicitly cut from the trait system for having no real statistical shadow to measure. If direct override/compliance-forcing is ever wanted later, it would reopen that question.

## Open connection to the (not-yet-designed) development engine

Tendencies should be able to shift based on sustained system exposure, but faster than a multi-season timescale — within a season, potentially noticeable within weeks or a handful of games. This suggests a **two-speed model** when the development engine gets designed in full:

- **Stable baseline tendency** — a player's true, core identity; changes slowly, mainly through career-level development/aging
- **Faster-moving "current adaptation" layer** on top of it — responds to recent real usage (how often a player has actually been put in a given role/context lately, and how it's gone), shifting the *effective* in-game tendency faster than the baseline itself moves

Not designed in detail yet — flagged as a hard constraint to carry into the full development-engine conversation when that topic is tackled. Open question for later: calibrate how fast "faster" actually is (noticeable within games vs. gradual over weeks/months of a season). The scheme/tactic familiarity mechanic below is the team-level counterpart of this same two-speed idea.

## Player roles: a real taxonomy, not invented

Grounded in the two real, data-driven NBA role-classification systems actually used in scouting/analytics (BBall Index's offensive archetypes and defensive roles, cross-checked against CraftedNBA's model) rather than freehanded media nicknames. These are the actual roles a player gets assigned to, independent of the coach's scheme choices above — the scheme decides how often a role's situations come up; the role decides which player is fed into them.

**Offensive roles:**
- **Primary Ball Handler** — leads initiation, highest on-ball reps
- **Secondary Ball Handler** — shares playmaking load, lower isolation/initiation rate than the primary
- **Shot Creator** — high personal isolation usage, perimeter or interior
- **Connector** — links the offense together; moves the ball, keeps possessions flowing, doesn't create from scratch
- **Slasher** — high tendency to attack the rim off the dribble
- **Athletic Finisher** — off-ball cutter/lob catcher who does damage through activity, not creation
- **Off-Screen Shooter** — scores mostly coming off screens/hand-offs, moving into the shot
- **Movement Shooter** — shooter who relocates constantly rather than standing still
- **Spot-Up Shooter** — catch-and-shoot from a stationary position
- **Versatile Big** — does everything: shoots, posts up, screens, finishes
- **Post Scorer** — back-to-basket usage, low 3PA
- **Stretch Big** — floor-spacing big, low post usage, high 3PA
- **Roll & Cut Big** — finishes at the rim off dives/dump-offs, minimal shooting or post game

**Defensive roles (one complete real taxonomy — BBall Index's 7):**
- **Point of Attack** — guards the ball handler in on-ball actions, little off-ball help duty
- **Chaser** — sticks to shooters/cutters off-ball, little on-ball duty
- **Helper** — rotates and digs in from the weak side constantly; lives in gaps and rotations
- **Low Activity** — light defensive assignment, not screen-involved or help-heavy
- **Wing Stopper** — guards shot creators on the wing, mixes on-ball toughness with some help responsibility
- **Mobile Big** — switches/hedges out to the perimeter in ball screens
- **Anchor Big** — drops deep, protects the rim

## Position vs. role

Position (PG–C) is not a behavioral category — it's a **physical sizing reference only**: it sets the baseline defensive matchup assignment (who guards who by size, before any scheme adjusts it) and feeds the raw Height/Wingspan numbers into move resolution (e.g. the reach-differential modifier in the possession-engine doc). It does **not** gate what lineups are legal to field. Role (the taxonomy above) is the actual behavioral assignment, and it's fully position-agnostic — matching the instinct that role matters more than position. A 6'8" forward who's genuinely a Primary Ball Handler is a legitimate "point forward"; that's not a new role, it's a role/position combination the taxonomy already covers without needing a dedicated name for it.

## Multi-role tagging (how real hybrids work without inventing new categories)

A player is assigned **one primary and one optional secondary role per side of the ball**, not locked to a single label. A "3-and-D wing" is Spot-Up Shooter (primary offense) + Chaser or Wing Stopper (primary defense). A "swiss-knife" big is Versatile Big + Mobile Big. This covers every real hybrid combination without a combinatorial explosion of named archetypes — the taxonomy stays small and fixed, and the hybrids emerge from tagging, the same way traits emerge from real statistical distance rather than being hand-picked per player.

## Tactical knobs: 5-tier dials

Team-level tactical knobs — pace, inside/outside balance, floor spacing, defensive pressure, help aggressiveness, and similar levers — are each a **1–5 dial, with 3 as league-average/neutral**, reusing the trait system's spectrum-with-neutral-middle shape rather than inventing a new interface pattern for tactics.

## Scheme & tactic familiarity: the team-level two-speed layer

The two-speed tendency idea flagged above for player development has a direct team-level counterpart. Every installed tactic/scheme has a **familiarity meter**, starting low on install and ramping up with real reps (practice time and/or actual games run in it). Familiarity scales how fully a tactic's tendency-shifts and scheme executions actually land in a game — a freshly installed defensive scheme only delivers its design's full *intent* partially; a scheme the team has run all season executes at full strength. This is genuinely the same mechanic as the player-level two-speed idea, one level up, not a new one — and it directly answers "a team shouldn't execute a newly installed tactic as well as one they've drilled."

## Lineup chemistry: a separate meter from scheme familiarity

Scheme familiarity measures whether the *team* knows a tactic. Lineup chemistry measures something distinct: whether *these specific players*, on the floor together, have real reps as a combination. Two individually great, scheme-fluent players can still be clunky together early — mistimed passes, a blown rotation on a closeout, a cut into the space a teammate was also relocating to — purely because they haven't logged minutes as a pairing/group yet, independent of how good either of them is individually or how well either knows the scheme.

Mechanically, this is the same shape as everything else here rather than a new concept: a **familiarity meter per meaningful player combination** (the starting five, and probably any 2–3 player sub-combination that shares the floor a lot, like a starting backcourt), starting low for a brand-new pairing/group and ramping with actual shared minutes played, which scales the quality of chemistry-dependent resolutions (passing-move accuracy, off-ball rotation timing, closeout/help positioning) slightly up or down. A roster that gets reshuffled constantly (trades, injuries forcing new lineups) should feel measurably worse at this than a roster that's run the same five together all year — genuinely, not just flavor text, the same bar the mismatch-amplification rule holds everything else to.

This resolves what "formation" actually needed: fielding any five players was never a legality question (see Position above — nothing blocks a five-center lineup; the engine just punishes the spacing/matchup consequences through the existing attribute and mismatch-amplification machinery). The one real, previously-missing piece was this chemistry meter, now captured.

## Defensive schemes & situational calls (real, named)

This is the actual content "defense should be fully customizable" was missing — a real, named list rather than loose examples:

- **Base schemes:** Man-to-man, Switch Everything, Drop Coverage, ICE/Weak (forces ball screens away from the strong side), Blitz/Trap, Full-court press, Pack-the-Paint/No-Middle
- **Zones:** 2-3, 3-2, 1-3-1, Box-and-1, Triangle-and-2
- **Situational calls** (layered on top of a base scheme for specific game moments, each with its own familiarity ramp): end-of-quarter, late-shot-clock, BLOB/SLOB (baseline/sideline out-of-bounds), last-possession-of-game

## Mismatch amplification is a hard requirement, not a vibe

Fully specified in the possession-engine doc's combination-mechanics section, but the reason it lives here too: a poor Point of Attack defender running Drop Coverage against an elite movement/pull-up shooter has to produce a genuinely lopsided result once the resolution formulas are fit — not a mild statistical bump. That's the actual bar every move's resolution formula gets held to, and it's what makes the role, scheme, and matchup choices above matter inside the sim rather than being flavor text layered on top of it. The same bar applies to lineup-level size mismatches (a small-ball lineup getting posted up) exactly as it applies to scheme-level ones (bad coverage vs. a great shooter).

## Still open

- Exact list of which tactical knobs exist beyond the examples named above
- How in-game, mid-possession coach adjustments (timeouts, late-game ATOs) interact with the familiarity meter in the moment, versus familiarity only mattering for pre-set schemes
- Rotation/substitution logic (fatigue/stamina, foul trouble, bench depth, matchup-hunting substitutions) — real and undesigned, but bigger than tactics and deserves its own dedicated pass
