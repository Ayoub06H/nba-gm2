# Trade Logic & Front Office

## Core premise this system serves

The player is the first-ever "GM coach" — a single role combining front-office and head-coaching duties that in reality are always separate people with different incentives. **Decision locked: every AI-controlled team runs one unified AI "brain"** making both front-office and coaching decisions for that team, rather than two separate competing AI decision-makers. Simpler to build, and every AI team stays internally consistent — a team benching or shopping a player reflects one coherent view of him, not two AI roles working at cross purposes.

## Player valuation: the required foundation

Everything else in this doc — trade finder, trade evaluation, AI-to-AI trades — needs a real, data-driven "how valuable is this player" number to operate on. It's built from pieces already locked elsewhere in this design, not invented fresh:
- **On-court performance**, from the attribute/tendency/possession-engine output (real simulated production, not a hand-picked rating)
- **Contract value against the cap rules** — what he costs relative to what that production would cost on the open market, using the cap/apron structure already locked
- **Age-curve trajectory** from the development/progression doc — a player's trend line matters as much as his current level (rising 23-year-old vs. declining 33-year-old at equal current output are not equally valuable)
- **Scouting confidence** — how much of this valuation is known vs. estimated (ties into the scouting system below; a highly scouted player's value is a tighter, more trustworthy number than a thinly-scouted one)

This produces a **base value**, which the rest of the system does not treat as the final price.

## Leverage: the actual driving force behind a trade

"Why would I trade X?" is the real question underneath almost every NBA trade, and it's a separate axis from base value, not a replacement for it. Two players with identical base value can have wildly different real trade prices depending on each side's leverage. Mechanically, leverage is a **contextual modifier on top of base value**, same baseline-plus-modifier shape used everywhere else in this design (tendencies vs. coaching system, development baseline vs. context) — and like the mismatch-amplification rule in the possession engine, extreme leverage situations should produce real, compounding discounts or premiums, not small ones.

**Real factors that move leverage, in either direction:**
- **Contract runway** — more years of team control = more leverage for the team holding him; an expiring/rental contract collapses the holding team's leverage, since the alternative is losing him for nothing
- **Public trade-request status** — once it's known league-wide that a player wants out, the holding team's leverage craters; everyone knows they must sell
- **Competitive-timeline fit** — a rebuilding team with no urgency can wait for a great offer (high leverage); a team facing immediate pressure (injury-depleted, apron-squeezed, fighting for a playoff spot at the deadline) is a forced actor with low leverage
- **Cap/apron pressure** — a team forced to shed salary to escape second-apron restrictions (per the cap doc) has reduced leverage regardless of the player's actual basketball value; they may need to sell below fair value just to create outcomes room
- **Scarcity of the player's role/archetype** — reusing the role taxonomy from the tactics doc: a true Anchor Big or Primary Ball Handler in a market thin on that role commands a real premium, independent of his raw rating
- **Public trade-block listing has a real leverage cost** — this is a deliberate, concrete consequence rather than a free action: listing a player as available signals the rest of the league that you're motivated to move him, which should mechanically reduce the leverage you can command for him. Shopping a player quietly (or not at all, forcing other teams to call you) should preserve leverage; broadcasting availability should cost it.

## Trade evaluation: grading a specific proposed deal

A proposed trade is graded per side as: **base value of what's received** vs. **base value of what's given up, adjusted by each team's current leverage.** A team with low leverage accepting a deal that's a mild loss on raw value can still be a "good" trade for them given their actual situation (forced seller getting a fair outcome under pressure) — the evaluation needs to reflect that, not just compare raw value totals. This is also where the second-apron trade-matching restrictions from the cap doc apply as hard constraints on what's even a legal proposal before evaluation happens.

## Trade finder

Searches for realistic trade packages that would score well under the evaluation above, from either side's perspective. A well-built finder should naturally surface low-leverage sellers as good targets — exactly how real GMs operate, hunting for a team that's a forced actor rather than offering fair value to a team under no pressure to sell.

## Trade blocks & untouchables

Two flags on a player, not new mechanics on top of the above — they feed directly into the leverage and evaluation systems already described:
- **Trade block** — marks a player as available; per the leverage section, this is not a free flag, it carries a real leverage cost once public
- **Untouchable** — removes a player from trade-finder/AI-offer consideration entirely, independent of what his value or leverage situation would otherwise suggest

## Shortlists

The lightest item here — a separate, user-curated list of players to track and navigate to easily (scouting targets, trade targets, future free agents), with no independent mechanic of its own. Pure UI/organization on top of the systems above.

## AI-to-AI trades

Not a separate system — AI teams run the same base-value-plus-leverage evaluation the player does, and propose/accept deals accordingly, as one unified AI brain per team (per the premise decision above). The interesting case is two AI teams with mismatched leverage (a forced seller and a patient buyer) producing a real, lopsided-but-rational trade between them, visible to the player as league activity, not just a background event.

## Scouting

Applies to **every NBA player, not just draft prospects**, and reuses a mechanism already locked rather than inventing a new one. Two things are always true about any player, scouted or not:

- **His real box score and advanced stats are always fully visible to everyone.** Nothing hides observable, already-happened production — that's real data, not something to fog.
- **His underlying hidden attributes are never directly visible.** What you see instead is an estimated range (e.g. 64-74 on a given attribute), not the true number.

**The starting estimate, before any scouting investment at all, is the same comp-lookup the prospect-generation system already does**: run the player's real stats back through the statistical-comp model to produce an initial range. A veteran with years of heavy-minutes production gets a fairly tight band this way for free; an unproven bench player with thin data gets a wide one. No separate "unscouted = total blank" state — the engine already has enough signal in real production alone to produce a first estimate for anyone.

**Actual scouting investment (game tape, private workouts, practice/film access) narrows that range toward the true values over time.** Your own roster should narrow faster than the rest of the league by default — you have daily practice and film access to your own players that you don't have to anyone else's — so a player you've rostered for two seasons should be a tighter, more trustworthy number than an opposing player you've only ever scouted from the outside.

This directly feeds the "scouting confidence" input to player valuation above: a thinly-known player's valuation carries real, visible uncertainty, not a false-precision single number.

## Day-to-day structure (presentation layer, not a new mechanic)

A navigable calendar (Football Manager-style) is the backbone of the day-to-day loop — every game, every transaction, every scouting report lands on a date on it. A social media/news feed sits on top of the simulation as a *consumer* of it, not a new system: interviews, press conferences, standout/underdog performances, and award-race chatter are all narrative surface over events the simulation already produces (a box score outlier, an award model's current leader, a team's win/loss swing), not independently simulated content.

## Still open

- **Scouting investment mechanics** — what actually consumes scouting resources/time (a scouting department, budget, staff with their own skill ratings?) and the exact rate at which the range narrows per unit of investment
- **Award-race and news-trigger logic** — what specifically promotes a performance or storyline into the social media feed, and how an in-sim awards model (MVP race, etc.) gets computed in the first place
- **Exact leverage formula** — the factors above are real and locked conceptually, but the actual weighting/combination (same "interaction effects, not flat addition" principle as the possession engine) isn't quantified yet
