namespace NbaGm.Core.Model;

/// <summary>
/// Position exactly as the NBA publishes it (doc 11): one of G, F, C, G-F, F-C, C-F, F-G.
/// It is a physical sizing reference only (doc 06). <see cref="Index"/> orders the label along
/// the guard-to-center axis, with a pair counted the same in either order; default matchups
/// pair a defender with the attacker of the closest index, ties broken by the smaller height
/// difference.
/// </summary>
public sealed record Position
{
    private static readonly Dictionary<string, int> Indexes = new()
    {
        ["G"] = 1,
        ["G-F"] = 2,
        ["F-G"] = 2,
        ["F"] = 3,
        ["F-C"] = 4,
        ["C-F"] = 4,
        ["C"] = 5,
    };

    public Position(string label)
    {
        if (!Indexes.TryGetValue(label, out var index))
        {
            throw new ArgumentException($"'{label}' is not one of the seven published position labels", nameof(label));
        }
        Label = label;
        Index = index;
    }

    public string Label { get; }

    /// <summary>G=1, G-F/F-G=2, F=3, F-C/C-F=4, C=5.</summary>
    public int Index { get; }

    public static IReadOnlyCollection<string> Labels => Indexes.Keys;

    public override string ToString() => Label;
}
