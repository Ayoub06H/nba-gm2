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
        Assert.Equal(28, AttributeSet.Count);
        Assert.Equal(21, TendencySet.Count);
        Assert.Equal(5, TraitSet.Count);
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
