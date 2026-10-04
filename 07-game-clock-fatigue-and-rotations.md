
# Game Clock, Fatigue & Rotations

## Why this is the connective tissue, not a side system

The possession engine defines *what* happens on any given possession. This layer defines *when*, *for how long*, *who's actually on the floor*, and *how fresh they are* — the thing that actually turns a list of possessions into a playable 48-minute game. Four decisions below are locked.

## Real game-clock seconds

Each possession consumes a variable, real amount of game-clock time — not an abstract possession count. This plugs directly into the **Shot Clock Usage** tendency already locked in the attribute/tendency doc (early-clock vs. late-clock shot hunting is literally what determines how long a possession actually takes), and the chained moves within a possession (drive, screen navigation, kick-out, re-post, etc.) consume realistic time off the clock as they resolve.

Standard structure: four 12-minute quarters, 5-minute overtime periods, a 24-second shot clock with a 14-second reset after an offensive rebound, and real stoppage time from timeouts/fouls/out-of-bounds. This is what makes the tactics doc's situational calls (end-of-quarter, late-shot-clock, last-possession-of-game) trigger off **real, checkable clock state** — "under :30 and down 3" — rather than an abstract flag.

## Fatigue: a real decaying resource tied to Stamina

Same baseline-plus-modifier shape used everywhere else in this design: a player's raw attributes are his baseline, and accumulated in-game exertion (recent minutes/possessions played, not just total minutes tonight) pushes his *effective* attributes down from that baseline as the game goes on, recovering while he's on the bench.

The **Stamina** attribute (already locked under Physicals) governs both sides of this in one stat: high Stamina means slower decay under load and faster recovery on the bench; low Stamina means the opposite. This is what makes the rotation plan's bench-timing choices actually matter mechanically — riding a low-Stamina starter too long has a real, visible cost (degraded effective attributes in exactly the moments that matter most), not a soft suggestion to rest him.

## Foul trouble: a real decision point, and a real thing to exploit

6-foul disqualification stays exactly as the real rule. Foul trouble is a genuine bench-or-play tradeoff — pulling an early-foul-trouble player protects him for winning time at the direct cost of his minutes right now — and needs to be a visible, reactable game state (see Rotations below), not just a number climbing in a box score.

**The exploitation case:** an offense with a high-Offensive-IQ ball handler should recognize an opponent in foul trouble and deliberately attack him more. This isn't a new mechanic bolted on — it's the three-layer attribute/tendency pipeline already locked (tendency decides what's attempted; IQ acts as the quality gate on *when* that's a good idea, reading live game state) doing exactly the job it was built for. Offensive IQ reading "this specific defender is in foul trouble" and biasing the attack-the-mismatch decision toward him is one more real input into a system that already exists, not a special case.

The mirror case on defense: a player in foul trouble should play more cautiously, and that should show up as a real, situational shift in his own defensive tendencies in the moment — more conservative closeouts, more likely to go under a screen than fight over it, lower Gamble-for-Steals — rather than an invented flat "foul trouble debuff." Reuses the tendency system instead of adding a new modifier type.

## Rotations: a pre-set plan plus reactive overrides

Before the game: a depth chart/rotation plan — who plays which stretches of minutes, organized by role (ties into the role taxonomy from the tactics doc) — that the engine follows as its default. In-game, that plan is a default, not a script: real conditions override it —
- Foul trouble (above)
- Fatigue crossing a threshold (above)
- Blowout garbage time
- Injury
- Matchup-hunting substitutions (subbing in a specific defender based on who the opponent currently has on the floor, tying back to the role/mismatch system already locked)

This is the same friction-between-plan-and-reality principle used everywhere else in this design: the rotation plan is the coach's intent, live game state is reality, and the two can genuinely conflict — exactly like a tactical system can conflict with a player's own tendencies, or a trade's "fair value" can conflict with a team's actual leverage.

## Still open

- Exact fatigue decay/recovery curve (effective-attribute cost per minute of load at a given Stamina level, and recovery rate on the bench) — a calibration question for later, same treatment as the possession-engine's per-move formulas
- Exact foul-trouble thresholds that count as "trouble" (e.g. 2 fouls in the first quarter, 4 by halftime) and how aggressively default AI substitution logic reacts to them versus waiting for explicit player instruction
- Garbage-time/blowout substitution threshold (margin + time remaining that triggers bench-clearing) — not yet defined
- How much of the reactive substitution logic is the player's own configurable rule set (e.g. "always protect a starter from fouling out before the 4th quarter") versus built-in default AI behavior
