namespace NbaGm.Core.Model;

/// <summary>Raw biometric inputs (doc 01): not rated, read directly by later calculations.</summary>
public sealed record Measurables(double HeightIn, double WeightLb, double WingspanIn, bool WingspanImputed);

/// <summary>Contract stub (doc 11): per-season salary and years remaining. Not exercised yet.</summary>
public sealed record Contract(double Salary, int YearsRemaining);

/// <summary>Real 2025-26 usage with the current team; drives the default rotation (doc 11).</summary>
public sealed record SeasonUsage(int GamesPlayed, int GamesStarted, double MinutesPerGame, int DepthRank);

public sealed class Player
{
    public required int Id { get; init; }
    public required int TeamId { get; init; }
    public required string FirstName { get; init; }
    public required string LastName { get; init; }
    public string? Jersey { get; init; }

    /// <summary>Position as stats.nba.com publishes it (G, F, C, G-F, F-C, ...).</summary>
    public string? ListedPosition { get; init; }

    /// <summary>PG-C sizing reference (doc 11). Null until its source is specified (GAPS.md G20).</summary>
    public Position? Position { get; init; }

    public required Measurables Measurables { get; init; }
    public required AttributeSet Attributes { get; init; }
    public required TendencySet Tendencies { get; init; }
    public required TraitSet Traits { get; init; }
    public required SeasonUsage Usage { get; init; }

    /// <summary>Null until a salary source is specified (GAPS.md G21).</summary>
    public Contract? Contract { get; init; }

    public string FullName => $"{FirstName} {LastName}".Trim();

    public override string ToString() => FullName;
}
