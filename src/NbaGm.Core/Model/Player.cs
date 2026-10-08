namespace NbaGm.Core.Model;

/// <summary>Raw biometric inputs (doc 01): not rated, read directly by later calculations.</summary>
public sealed record Measurables(double HeightIn, double WeightLb, double WingspanIn, bool WingspanImputed);

/// <summary>Contract stub (doc 11): per-season salary and years remaining, both nullable and
/// filled only from a named real source. Nothing in Phases 1-3 reads them.</summary>
public sealed record Contract(double? Salary, int? YearsRemaining);

/// <summary>Real 2025-26 usage with the current team; drives the default rotation (doc 11).</summary>
public sealed record SeasonUsage(int GamesPlayed, int GamesStarted, double MinutesPerGame, int DepthRank);

public sealed class Player
{
    public required int Id { get; init; }
    public required int TeamId { get; init; }
    public required string FirstName { get; init; }
    public required string LastName { get; init; }
    public string? Jersey { get; init; }

    /// <summary>Published position label and its guard-to-center index (doc 11).</summary>
    public required Position Position { get; init; }

    public double? Age { get; init; }

    /// <summary>
    /// No on-floor exposure in 2025-26 (doc 02 "Population"). Such a player's rated attributes
    /// are all the temporary placeholder <see cref="PlaceholderRating"/>, his tendencies are the
    /// prior rates and he has no traits.
    /// </summary>
    public bool NoData { get; init; }

    /// <summary>Every rated attribute is the placeholder value, not a derived rating.</summary>
    public bool HasPlaceholderRatings { get; init; }

    public const double PlaceholderRating = 40.0;

    public required Measurables Measurables { get; init; }
    public required AttributeSet Attributes { get; init; }
    public required TendencySet Tendencies { get; init; }
    public required TraitSet Traits { get; init; }
    public required SeasonUsage Usage { get; init; }

    /// <summary>Null until a real salary source is named (doc 11).</summary>
    public Contract? Contract { get; init; }

    public string FullName => $"{FirstName} {LastName}".Trim();

    public override string ToString() => FullName;
}
