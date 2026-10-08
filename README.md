# NBA GM simulation

A real-data NBA GM simulation in C#. The design lives in the eleven numbered docs at the repo root;
`11-phase-1-3-build-and-data-pipeline-plan.md` sets the build order.

## Phase 1: the real league, loaded (in progress)

All 30 teams and every 2025-26 rostered player, with Attributes, Tendencies and Traits derived
purely from real statistics (docs 02-04). Nothing is simulated yet.

| Part | Where |
|---|---|
| Data gathering (runs on your machine) and derivation | `pipeline/` (see `pipeline/README.md`) |
| League database schema (shared by Python and C#) | `schema/league.sql` |
| Derived league file, committed after the local run | `data/league_2025_26.sqlite` |
| C# data model and loader | `src/NbaGm.Core` |
| Phase 1 definition-of-done check | `tools/NbaGm.Phase1Check` |
| Open questions on the docs, and mechanical readings | `pipeline/GAPS.md` |

```bash
dotnet test                                    # C# model/loader tests
cd pipeline && python -m pytest                # pipeline tests (incl. a full synthetic build)
dotnet run --project tools/NbaGm.Phase1Check   # check data/league_2025_26.sqlite
```

`LeagueLoader.Load` refuses to load a league file in which any player is missing a value. The one
placeholder allowed is doc 02's temporary 40.0 for rostered players with no 2025-26 exposure, which
is flagged on the player (`NoData`, `HasPlaceholderRatings`).
