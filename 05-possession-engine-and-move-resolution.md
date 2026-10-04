
# Possession Engine & Combination Mechanics

## Why anything is "hardcoded" at all

No simulation can exist with zero fixed structure — the same way real basketball has a fixed rulebook (shot clock, travel, court dimensions) but is never "static," because the rulebook doesn't decide who wins. The actual players do. The design goal here is the same: keep the hardcoded part as small and general as possible (the rulebook), and push everything else — who does what, how well it goes — into real player data and randomness.

## What's hardcoded vs. what emerges

**Hardcoded (fixed, same for every player/game, forever):**
1. The menu of possible moves (below)
2. Which attributes/inputs are relevant to each move
3. The shape of the formula that turns those inputs into a probability
4. Basic basketball rules — what's legal when, how a move's result changes the game state

**NOT hardcoded (varies every time, driven by real data + randomness):**
1. Which move gets picked at any decision point — driven by that specific player's tendency values + live context + a random roll
2. How well a chosen move goes — driven by that specific player's (and opponent's) actual attribute values + a random roll
3. The sequence of moves in any given possession — emerges from chaining many individually non-hardcoded picks/outcomes
4. Any actual stats, player identities, or league averages — pure outputs of running real/generated data through the fixed machinery many times

## Possession structure: a small set of moves, chained dynamically

A possession is not one single formula — it's a sequence of small, distinct moments ("moves"), where each move's outcome becomes the context for the next. Nothing is scripted per-situation; the situational richness comes from how a small, fixed list of moves gets chained differently every time by the players actually involved.

## Move list (LOCKED — cross-checked against every locked attribute and tendency)

Two different kinds of things, kept separate: **moves** (things a player actively chooses to attempt) and **resolution outcomes** (what can result once a move is attempted — not a choice, what the dice roll produces).

### On-ball offensive moves
- **Drive** — attacks the rim off the dribble. Crossovers, spins, hesitations, step-backs are flavor/animation of this same move, not separate primitives — they all pull Ball Handle vs. defender's On-Ball Defense/Lateral Quickness.
- **Pull-up jumper** — stops and shoots off the dribble (mid or three)
- **Catch-and-shoot** — shoots immediately off a pass, no dribble
- **Post-up** — backs down a defender, back to the basket
- **Pass** — sub-flavors pulling different attributes: standard/kick-out, post-entry, lob (pairs with receiver's Vertical/hands), full-court/outlet (distance/arm strength)
- **Hand-off** — dribble hand-off directly to a cutting teammate (distinct from a screen)
- **Call for / use a screen** — initiates or navigates a ball screen
- **Shot fake** — can bait a defender into a bad contest, enabling a follow-up

### Off-ball offensive moves
- **Cut** — basket cut, backdoor cut, or flash to the post
- **Set a screen** — on-ball or off-ball (e.g. a pindown); same resolution mechanics (screener vs. chasing defender) either way
- **Relocate / spot up** — moves to open space for spacing
- **Roll or pop** — the screener's choice right after setting a ball screen: dive to the rim (Finishing/Vertical) or pop for a jumper (Shooting) — a real, distinct decision, not just flavor

### Defensive moves
- **Contest a shot** — perimeter closeout (On-Ball Defense) or rim contest (Rim Protection)
- **Navigate a screen** — fight over, go under, switch, or hedge/show-and-recover (four distinct real schemes)
- **Help / rotate** — leaves an assignment to help a teammate
- **Recover / close the gap** — getting back to an assignment after helping or being beaten
- **Deny the pass** — actively denying an entry pass or cutter off-ball (Off-Ball Defense)
- **Gamble for a steal** — jumping a passing lane or digging at the ball
- **Draw a charge** — standing ground to draw an offensive foul
- **Box out / contest rebound** — defensive rebounding
- **Post defense** — guarding the post, fronting or playing behind
- **Trap / double-team** — team-scheme decision; two defenders converge on the ball handler, modifying how the offensive move resolves rather than being its own offensive move

### Shared / either-side moves
- **Loose ball recovery / dive** — scramble moment involving players from both teams (ties to Hustle trait, Loose Ball tendency)
- **Jump ball** — start of game/overtime or held-ball situations, resolved by Vertical + Height of the players involved

### Special/situational moves (no live defender, low complexity)
- **Free throw** — resolved purely by the Free Throw attribute
- **Inbound pass** — after a made basket, violation, or start of a period

### Resolution outcomes (not choices — what a move's dice roll produces)
Make, miss, steal, turnover (bad pass, travel, offensive foul), block, shooting foul drawn, assist credit, shot clock violation, out of bounds. These attach to whichever move just resolved.

### Cross-check note
Every locked attribute (including Standing Dunk, which attaches to a Cut resolving into a catch-and-finish at the rim, distinct from Driving Dunk off a Drive) and every locked tendency has at least one move above it plugs into. Approved by user as complete for now.

## Combination mechanics: how multiple attributes resolve one moment

For any single move, several attributes act **simultaneously**, not sequentially (e.g. a contested finish combines Strength + Driving Layup + Touch into one joint outcome). The mechanism:

1. Normalize each relevant input
2. Combine them — ideally via a model/fit that can express real **interaction effects**, not just flat addition (two inputs can amplify or cancel each other, not just add)
3. Pass the combined result through a non-linear curve (sigmoid-style) to get a final probability
4. Roll against that probability for the actual outcome — the formula only ever produces a probability, never a guaranteed result, which is what keeps individual moments unpredictable despite a formula running underneath

### Worked example: height/reach interaction on a contested jump shot

A defender's On-Ball Defense rating reflects skill at getting into position and timing a contest — but whether that contest can physically reach the shooter's release point is a separate, geometric question, answered by raw Measurables (Height, Wingspan), not the skill rating. A great closeout from a much shorter defender should barely affect a tall shooter's release; the same closeout from a longer defender meaningfully contests it. Concretely:

`effective contest = On-Ball Defense × reach-differential modifier (defender's effective reach vs. shooter's release height)`

This is a genuine interaction effect (not additive), and it's exactly why Height/Wingspan were deliberately kept as raw data rather than folded into a rated attribute — this kind of calculation needs the literal numbers, not an abstract 0-99 score. The same logic applies to rim protection vs. a finisher's size, post-up mismatches, and rebounding position.

## Mismatch amplification: a required cross-check, not a vibe

A joint-attribute formula that blends inputs as a flat or near-flat average will under-produce real basketball's actual blowout cases. A poor Point of Attack defender (low On-Ball Defense/Lateral Quickness) matched against an elite movement/pull-up shooter, under a scheme that's a bad fit for that shooter (e.g. Drop Coverage conceding exactly the space that kind of shooter needs), shouldn't just shoot a few points better than average — the real effect compounds: bad scheme fit × bad individual matchup × elite skill produces a genuinely lopsided result, not a mild bump. This is the concrete, practical case the "interaction effects, not flat addition" requirement above exists to guarantee. If a move's formula is ever implemented as a simple weighted sum instead, this exact scenario quietly stops being true, and the sim ends up feeling flat with no obvious bug to point at — role, scheme, and matchup choices stop mattering without anyone having broken a single rule explicitly.

**Cross-check rule, applied to every move's resolution formula once it's fit:** for any move where the attacker and defender have sharply asymmetric attribute profiles relevant to that move, validate the formula's output against a known real-world blowout case for that matchup type — not just checked against reasonable league-average output. If the formula can't reproduce "elite shooter + bad scheme fit + weak individual defender = a genuinely bad defensive outcome," the interaction term is wrong, not the scenario. This is the same validation-loop principle described below (comparing simulated distributions to real ones), applied specifically to mismatch scenarios rather than only aggregate averages — aggregate validation can look healthy while still averaging away exactly the extreme cases that make the sim feel authentic.

## Where the formula weights/parameters come from

Not hand-picked. Fit from real data the same way attribute values are:
- Rich-data actions (shooting: shot charts + defender-distance tracking available) — fit via regression/model against real outcomes, letting the data reveal real interaction effects (like the height one above) rather than requiring every interaction to be hand-anticipated.
- Thin-data actions (help-defense timing, screen navigation specifics) — start from a reasoned structure, refine later against the simulation's own validation harness once there's enough data (real or self-generated) to fit against.

## Why this doesn't need to be perfect on day one

- The granular attribute/tendency split already does most of the "nuance" work — many narrow inputs feeding a simple formula beats a few blended inputs feeding a complex one.
- The validation loop (comparing simulated output distributions to real ones, from the very first match-engine conversation) is what catches missing nuance — a flat/wrong interaction shows up as a visible mismatch to go fix, not a silent failure.
- Refinement is expected to be incremental and uneven: well-tracked actions (shooting) get rich and well-calibrated fast; thinner-data actions start cruder and improve over time.

## Still open
- Exact set of inputs/interaction terms per move type, to be defined move-by-move.
