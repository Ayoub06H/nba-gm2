namespace NbaGm.Core.Model;

public sealed class Team
{
    public required int Id { get; init; }
    public required string Abbreviation { get; init; }
    public required string City { get; init; }
    public required string Name { get; init; }

    /// <summary>Roster in depth-chart order: inferred starters first, then by minutes per game.</summary>
    public required IReadOnlyList<Player> Roster { get; init; }

    public IEnumerable<Player> Starters => Roster.Take(5);

    public override string ToString() => $"{City} {Name}";
}

/// <summary>A real 2025-26 regular-season game (the Phase 3 schedule).</summary>
public sealed record Game(string Id, DateOnly Date, int HomeTeamId, int AwayTeamId, int? HomePoints, int? AwayPoints);

public sealed class League
{
    public required string Season { get; init; }
    public required IReadOnlyList<Team> Teams { get; init; }
    public required IReadOnlyList<Game> Schedule { get; init; }

    private Dictionary<int, Player>? _playersById;
    private Dictionary<int, Team>? _teamsById;

    public IEnumerable<Player> Players => Teams.SelectMany(t => t.Roster);

    public Player Player(int id) => (_playersById ??= Players.ToDictionary(p => p.Id))[id];

    public Team Team(int id) => (_teamsById ??= Teams.ToDictionary(t => t.Id))[id];
}
