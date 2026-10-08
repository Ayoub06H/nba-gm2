namespace NbaGm.Core.Model;

/// <summary>
/// A player's 27 rated attributes. Values are unrounded doubles on the 0-99 display range
/// (doc 11 "Internal attribute storage"); round only when displaying.
/// </summary>
public sealed class AttributeSet
{
    private readonly double[] _values;

    public AttributeSet(IReadOnlyDictionary<AttributeId, double> values)
    {
        _values = new double[Count];
        foreach (var id in Enum.GetValues<AttributeId>())
        {
            if (!values.TryGetValue(id, out var v))
            {
                throw new ArgumentException($"missing attribute {id}", nameof(values));
            }
            if (double.IsNaN(v) || v < 0 || v > 99)
            {
                throw new ArgumentOutOfRangeException(nameof(values), v, $"{id} must be in [0, 99]");
            }
            _values[(int)id] = v;
        }
    }

    public static int Count { get; } = Enum.GetValues<AttributeId>().Length;

    public double this[AttributeId id] => _values[(int)id];

    public int Display(AttributeId id) => (int)Math.Round(_values[(int)id], MidpointRounding.AwayFromZero);
}

/// <summary>A player's tendencies: each the shrunk real rate in [0, 1] (doc 03), no curve reshaping.</summary>
public sealed class TendencySet
{
    private readonly double[] _values;

    public TendencySet(IReadOnlyDictionary<TendencyId, double> values)
    {
        _values = new double[Count];
        foreach (var id in Enum.GetValues<TendencyId>())
        {
            if (!values.TryGetValue(id, out var v))
            {
                throw new ArgumentException($"missing tendency {id}", nameof(values));
            }
            if (double.IsNaN(v) || v < 0 || v > 1)
            {
                throw new ArgumentOutOfRangeException(nameof(values), v, $"{id} must be in [0, 1]");
            }
            _values[(int)id] = v;
        }
    }

    public static int Count { get; } = Enum.GetValues<TendencyId>().Length;

    public double this[TendencyId id] => _values[(int)id];
}

/// <summary>
/// One trait (doc 04): the underlying shrunk real value (null for a player with no data), its
/// distance from the reference in SDs, and the five-position tier (-2..2, 0 = no trait).
/// </summary>
public sealed record Trait(double? Value, double ZScore, int Tier, string? TierName)
{
    public bool HasTrait => Tier != 0;
}

public sealed class TraitSet
{
    private readonly Trait[] _values;

    public TraitSet(IReadOnlyDictionary<TraitId, Trait> values)
    {
        _values = new Trait[Count];
        foreach (var id in Enum.GetValues<TraitId>())
        {
            if (!values.TryGetValue(id, out var t))
            {
                throw new ArgumentException($"missing trait {id}", nameof(values));
            }
            if (t.Tier is < -2 or > 2)
            {
                throw new ArgumentOutOfRangeException(nameof(values), t.Tier, $"{id} tier must be in [-2, 2]");
            }
            _values[(int)id] = t;
        }
    }

    public static int Count { get; } = Enum.GetValues<TraitId>().Length;

    public Trait this[TraitId id] => _values[(int)id];
}
