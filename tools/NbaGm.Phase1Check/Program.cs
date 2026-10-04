using NbaGm.Core.Data;

// Phase 1 definition-of-done check (doc 11) for a league file written by pipeline/build.py.
// Exit code 0 only when every rostered player has a real derived value for every attribute,
// tendency, trait and measurable, and the file loads into the C# model.

var path = args.Length > 0 ? args[0] : Path.Combine("data", "league_2025_26.sqlite");
var report = CompletenessReport.Read(path);
Console.Write(report);
if (!report.IsPhase1Complete)
{
    return 1;
}

var league = LeagueLoader.Load(path);
Console.WriteLine($"Loaded {league.Players.Count()} players on {league.Teams.Count} teams, " +
                  $"{league.Schedule.Count} scheduled games.");
return 0;
