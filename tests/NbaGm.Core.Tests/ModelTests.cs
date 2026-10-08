using NbaGm.Core.Model;

namespace NbaGm.Core.Tests;

public class ModelTests
{
    [Theory]
    [InlineData("OffensiveIq", "offensive_iq")]
    [InlineData("ThreePointer", "three_pointer")]
    [InlineData("CatchAndShootVsPullUp", "catch_and_shoot_vs_pull_up")]
    [InlineData("Streaky", "streaky")]
    public void Snake_case_matches_pipeline_keys(string pascal, string key) =>
        Assert.Equal(key, DbKeys.ToSnakeCase(pascal));

    [Fact]
    public void Every_key_round_trips_and_is_unique()
    {
        static void Check<TEnum>() where TEnum : struct, Enum
        {
            var keys = Enum.GetValues<TEnum>().Select(DbKeys.ToKey).ToList();
            Assert.Equal(keys.Count, keys.Distinct().Count());
            foreach (var id in Enum.GetValues<TEnum>())
            {
                Assert.True(DbKeys.TryParse<TEnum>(DbKeys.ToKey(id), out var back));
                Assert.Equal(id, back);
            }
        }
        Check<AttributeId>();
        Check<TendencyId>();
        Check<TraitId>();
    }

    [Fact]
    public void Locked_list_sizes()
    {
        Assert.Equal(27, AttributeSet.Count);
        Assert.Equal(20, TendencySet.Count);
        Assert.Equal(5, TraitSet.Count);
    }

    [Theory]
    [InlineData("G", 1)]
    [InlineData("G-F", 2)]
    [InlineData("F-G", 2)]
    [InlineData("F", 3)]
    [InlineData("F-C", 4)]
    [InlineData("C-F", 4)]
    [InlineData("C", 5)]
    public void Position_index_follows_doc_11(string label, int index)
    {
        var p = new Position(label);
        Assert.Equal(label, p.Label);
        Assert.Equal(index, p.Index);
    }

    [Fact]
    public void Unpublished_position_labels_are_rejected()
    {
        Assert.Throws<ArgumentException>(() => new Position("PG"));
        Assert.Equal(7, Position.Labels.Count);
    }

    [Fact]
    public void Attribute_values_keep_full_precision_and_round_only_for_display()
    {
        var values = Enum.GetValues<AttributeId>().ToDictionary(a => a, _ => 86.5);
        var set = new AttributeSet(values);
        Assert.Equal(86.5, set[AttributeId.Steals]);
        Assert.Equal(87, set.Display(AttributeId.Steals));
    }

    [Fact]
    public void Sets_reject_missing_and_out_of_range_values()
    {
        var attrs = Enum.GetValues<AttributeId>().ToDictionary(a => a, _ => 50.0);
        attrs[AttributeId.Vision] = 120;
        Assert.Throws<ArgumentOutOfRangeException>(() => new AttributeSet(attrs));

        var tends = Enum.GetValues<TendencyId>().ToDictionary(t => t, _ => 0.5);
        tends.Remove(TendencyId.CuttingFrequency);
        Assert.Throws<ArgumentException>(() => new TendencySet(tends));

        var traits = Enum.GetValues<TraitId>().ToDictionary(t => t, _ => new Trait(0, 0, 0, null));
        traits[TraitId.Clutch] = new Trait(0, 3, 3, "x");
        Assert.Throws<ArgumentOutOfRangeException>(() => new TraitSet(traits));
    }
}
