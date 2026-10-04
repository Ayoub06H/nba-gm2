# Salary Cap, CBA & Draft Lottery

## Core principle: the real current league rules, not invented ones

Same discipline as the role taxonomy and defensive schemes elsewhere in this design — these are rules the game enforces faithfully from the actual 2023 CBA and the actual, newly-reformed draft lottery, not simplified or invented approximations. **Decision locked:** the sim adopts the current/incoming rule set as its standing baseline going forward. It does not model the old pre-2027 lottery format as a historical transition period — the new system is simply "the rule," from the start of the sim.

## Salary cap & apron structure (2023 CBA)

Four thresholds, not one cap line (2025-26 real values, used as the sim's baseline — see growth note below):

- **Salary Cap: $154.647M** — soft cap, exceedable via exceptions below
- **Luxury Tax: $187.9M** — progressive penalty above this: $1.50/$ (first $5M over), $1.75/$ ($5-10M), $2.50/$ ($10-15M), $3.25/$ ($15-20M), $3.75+/$ (beyond), plus a repeater tax (~+$1.00/$ on top) for teams taxed in 4 of the prior 5 seasons. Half of all collected tax is redistributed to non-paying teams.
- **First Apron: $195.945M** — crossing this removes: the Non-Taxpayer MLE (Taxpayer MLE only remains), the Bi-Annual Exception, sign-and-trade eligibility, and tightens trade salary-matching from 125% to 110%.
- **Second Apron: $207.824M** — the hard-restriction tier: no MLE of any kind, no acquiring buyout-market players above the Taxpayer MLE salary, no aggregating multiple contracts to match salary in a trade, no sending cash in trades, trade matching caps at 100% (can't take back more than you send out). A team's own first-round pick 7+ years out becomes frozen/untradeable until the team dips below the second apron for at least one full season; stay above it 3 of 5 seasons and that future pick slides to 30th overall.

**Exceptions (2025-26 values):** Non-Taxpayer MLE $14.1M, Taxpayer MLE $5.6M, Bi-Annual Exception $5.1M, plus a minimum-salary exception available to every team regardless of cap situation. **Bird Rights** let a team re-sign its own free agent above the cap (full/early/non-Bird tiers differ in years of required continuous service).

**Trade salary-matching, by team cap status:** below first apron, outgoing salary can be matched up to 125% incoming; above first apron, 110%; above second apron, 100% (strictly no more incoming than outgoing).

**Cap growth is not flat** — a new TV deal roughly doubles league media revenue, so the cap is already projected to climb sharply: ~$170M (2026-27), ~$187M (2027-28), ~$206M (2028-29). Today's apron lines will fall *below* tomorrow's cap figure within a few simulated seasons, which the cap-growth model needs to account for rather than assuming a static number.

## Draft lottery: the 3-2-1 reform

Approved 29-1 by the Board of Governors, effective for the 2027 draft onward (this is the rule the sim uses from the start, per the decision above):

- Lottery pool expands from 14 to **16 teams**, now including the 9 and 10 play-in seeds
- Odds are deliberately non-monotonic by record — the actual anti-tanking mechanism, and worth preserving faithfully rather than simplifying into "worse record = better odds":
  - 3 worst-record teams: **5.4%** each at the No. 1 pick
  - Teams finishing 4th-10th worst: **8.1%** each — genuinely better odds than bottoming out
  - No. 9 / No. 10 play-in seeds: **5.4%** each
  - No. 7-vs-8 play-in game losers: **2.7%** each
- **Lottery floor:** the 3 worst-record teams can never fall below the No. 12 overall pick
- **No franchise can win back-to-back No. 1 picks**
- The league holds explicit disciplinary authority to reduce a team's odds or alter its draft position for deliberate tanking — flagged as optional below, since it's a real rule but a judgment-call mechanic to simulate, not a formula

Picks 5-14 within the lottery, and the full non-lottery order (11-14 or 15-30 depending on playoff/play-in result), follow the standard reverse-order-of-finish logic once the top-4 lottery results are drawn.

## Still open

- **Cap growth beyond 2028-29** — real projections only exist through that season; the sim needs an assumed growth-rate formula for anything simulated further out, since multi-decade saves will run past all currently known real numbers
- **Whether to simulate the league's tanking-discipline power** as an active mechanic (e.g. detecting suspicious lineup/rest patterns and penalizing odds) or leave it out as a rule that exists in reality but isn't worth the complexity to model
- **Everything this unlocks but doesn't itself design** — actual trade logic, free agency negotiation/AI, and contract-offer mechanics all need the cap/apron rules above as their foundation; trade logic itself is now designed in full in `10-trade-logic-leverage-and-scouting.md`
