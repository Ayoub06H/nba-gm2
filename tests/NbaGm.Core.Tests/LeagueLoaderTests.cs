using NbaGm.Core.Data;
using NbaGm.Core.Model;

namespace NbaGm.Core.Tests;

public class LeagueLoaderTests
{
    [Fact]
    public void Complete_file_loads_every_player_with_every_value()
    {
        using var db = new TestLeagueDb();
        var league = LeagueLoader.Load(db.Path);

        Assert.Equal("2025-26", league.Season);
        Assert.Equal(30, league.Teams.Count);
        Assert.Equal(30 * TestLeagueDb.PlayersPerTeam, league.Players.Count());

        var pid = TestLeagueDb.PlayerId(7, 2);
        var p = league.Player(pid);
        foreach (var a in Enum.GetValues<AttributeId>())
        {
            Assert.Equal(TestLeagueDb.AttributeValue(pid, a), p.Attributes[a]);
        }
        foreach (var t in Enum.GetValues<TendencyId>())
        {
            Assert.Equal(TestLeagueDb.TendencyValue(pid, t), p.Tendencies[t]);
        }
        Assert.Equal(1, p.Traits[TraitId.Hustle].Tier);
        Assert.Equal(76, p.Measurables.HeightIn);
        Assert.Equal("F-G", p.Position.Label);
        Assert.Equal(2, p.Position.Index);
        Assert.False(p.NoData);
        Assert.Null(p.Contract);
    }

    [Fact]
    public void Players_without_exposure_carry_the_flagged_placeholder()
    {
        using var db = new TestLeagueDb();
        var league = LeagueLoader.Load(db.Path);
        var p = league.Player(TestLeagueDb.PlayerId(5, TestLeagueDb.PlayersPerTeam - 1));
        Assert.True(p.NoData);
        Assert.True(p.HasPlaceholderRatings);
        Assert.All(Enum.GetValues<AttributeId>(), a => Assert.Equal(Player.PlaceholderRating, p.Attributes[a]));
        Assert.All(Enum.GetValues<TraitId>(), t => Assert.False(p.Traits[t].HasTrait));
        Assert.Null(p.Traits[TraitId.Durability].Value);
    }

    [Fact]
    public void Placeholder_flag_must_match_the_ratings()
    {
        using var db = new TestLeagueDb();
        db.Exec($"UPDATE player_attributes SET rating = 41 WHERE player_id = {TestLeagueDb.PlayerId(5, TestLeagueDb.PlayersPerTeam - 1)} " +
                "AND attribute = 'vision'");
        Assert.Throws<InvalidDataException>(() => LeagueLoader.Load(db.Path));
    }

    [Fact]
    public void Rosters_are_in_depth_chart_order_and_schedule_is_loaded()
    {
        using var db = new TestLeagueDb();
        var league = LeagueLoader.Load(db.Path);
        var team = league.Team(TestLeagueDb.TeamId(3));

        Assert.Equal(Enumerable.Range(1, TestLeagueDb.PlayersPerTeam), team.Roster.Select(p => p.Usage.DepthRank));
        Assert.Equal(5, team.Starters.Count());
        var game = Assert.Single(league.Schedule);
        Assert.Equal(new DateOnly(2025, 10, 21), game.Date);
        Assert.Equal(110, game.HomePoints);
    }

    [Fact]
    public void A_single_missing_value_blocks_loading_and_is_named_in_the_report()
    {
        using var db = new TestLeagueDb();
        db.Exec($"DELETE FROM player_tendencies WHERE player_id = {TestLeagueDb.PlayerId(0, 0)} " +
                "AND tendency = 'charge_taking_willingness'");
        db.Exec("UPDATE derivation_status SET status = 'failed', note = 'why' WHERE name = 'charge_taking_willingness'");

        var ex = Assert.Throws<IncompleteLeagueDataException>(() => LeagueLoader.Load(db.Path));
        var field = Assert.Single(ex.Report.Fields, f => !f.IsComplete);
        Assert.Equal("charge_taking_willingness", field.Key);
        Assert.Equal(30 * TestLeagueDb.PlayersPerTeam - 1, field.PlayersWithValue);
        Assert.Equal("why", field.Note);
        Assert.Contains("PHASE 1 NOT COMPLETE", ex.Message);
    }

    [Fact]
    public void Missing_rows_count_as_missing_values()
    {
        using var db = new TestLeagueDb();
        db.Exec($"DELETE FROM player_traits WHERE player_id = {TestLeagueDb.PlayerId(4, 4)} AND trait = 'streaky'");
        var report = CompletenessReport.Read(db.Path);
        Assert.False(report.IsPhase1Complete);
        Assert.Equal("streaky", Assert.Single(report.Fields, f => !f.IsComplete).Key);
    }

    [Fact]
    public void Keys_the_model_does_not_know_are_reported()
    {
        using var db = new TestLeagueDb();
        db.Exec($"INSERT INTO player_attributes (player_id, attribute, rating) VALUES ({TestLeagueDb.PlayerId(0, 0)}, 'jump_shot', 50)");
        var report = CompletenessReport.Read(db.Path);
        Assert.False(report.IsPhase1Complete);
        Assert.Contains(report.KeyMismatches, m => m.Contains("jump_shot"));
    }

    [Fact]
    public void Fewer_than_thirty_teams_is_not_complete()
    {
        using var db = new TestLeagueDb();
        foreach (var table in new[] { "player_attributes", "player_tendencies", "player_traits" })
        {
            db.Exec($"DELETE FROM {table} WHERE player_id IN (SELECT player_id FROM players WHERE team_id = {TestLeagueDb.TeamId(29)})");
        }
        db.Exec($"DELETE FROM players WHERE team_id = {TestLeagueDb.TeamId(29)}");
        Assert.False(CompletenessReport.Read(db.Path).IsPhase1Complete);
    }
}
