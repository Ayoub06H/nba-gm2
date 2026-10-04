using Microsoft.Data.Sqlite;
using NbaGm.Core.Model;

namespace NbaGm.Core.Tests;

/// <summary>Builds a small league file from the real schema (schema/league.sql) for tests.</summary>
internal sealed class TestLeagueDb : IDisposable
{
    public const int PlayersPerTeam = 6;
    public string Path { get; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(), $"league-{Guid.NewGuid():N}.sqlite");

    public TestLeagueDb()
    {
        using var con = Connect();
        Exec(con, File.ReadAllText(System.IO.Path.Combine(AppContext.BaseDirectory, "league.sql")));
        Exec(con, "BEGIN");
        Exec(con, "INSERT INTO meta VALUES ('season', '2025-26')");
        for (var t = 0; t < 30; t++)
        {
            var teamId = TeamId(t);
            Exec(con, $"INSERT INTO teams VALUES ({teamId}, 'T{t}', 'City{t}', 'Name{t}')");
            for (var k = 0; k < PlayersPerTeam; k++)
            {
                var pid = PlayerId(t, k);
                Exec(con, "INSERT INTO players (player_id, team_id, first_name, last_name, jersey, listed_position, " +
                          "height_in, weight_lb, wingspan_in, wingspan_imputed, games_played, games_started, " +
                          "minutes_per_game, depth_rank) VALUES " +
                          $"({pid}, {teamId}, 'F{pid}', 'L{pid}', '{k}', 'G', {74 + k}, {200 + k}, {78 + k}, {k % 2}, " +
                          $"80, {(k < 5 ? 80 - k : 0)}, {34 - k}, {PlayersPerTeam - k})");
                foreach (var a in Enum.GetValues<AttributeId>())
                {
                    Exec(con, $"INSERT INTO player_attributes (player_id, attribute, percentile, rating) VALUES " +
                              $"({pid}, '{DbKeys.ToKey(a)}', 0.5, {AttributeValue(pid, a)})");
                }
                foreach (var tn in Enum.GetValues<TendencyId>())
                {
                    Exec(con, $"INSERT INTO player_tendencies (player_id, tendency, value) VALUES " +
                              $"({pid}, '{DbKeys.ToKey(tn)}', {TendencyValue(pid, tn)})");
                }
                foreach (var tr in Enum.GetValues<TraitId>())
                {
                    Exec(con, $"INSERT INTO player_traits VALUES ({pid}, '{DbKeys.ToKey(tr)}', 0.1, 1.5, 1, 'Mild')");
                }
            }
        }
        foreach (var a in Enum.GetValues<AttributeId>()) Status(con, "attribute", DbKeys.ToKey(a));
        foreach (var t in Enum.GetValues<TendencyId>()) Status(con, "tendency", DbKeys.ToKey(t));
        foreach (var t in Enum.GetValues<TraitId>()) Status(con, "trait", DbKeys.ToKey(t));
        foreach (var m in new[] { "height_in", "weight_lb", "wingspan_in" }) Status(con, "measurable", m);
        Status(con, "player_field", "position");
        Status(con, "player_field", "contract");
        Exec(con, $"INSERT INTO games VALUES ('0022500001', '2025-10-21', {TeamId(0)}, {TeamId(1)}, 110, 104)");
        Exec(con, "COMMIT");
    }

    public static int TeamId(int t) => 1610612737 + t;
    public static int PlayerId(int t, int k) => 1000 + t * 10 + k;
    public static double AttributeValue(int pid, AttributeId a) => (pid % 50) + (int)a + 0.25;
    public static double TendencyValue(int pid, TendencyId t) => ((pid + (int)t) % 100) / 100.0;

    public void Exec(string sql)
    {
        using var con = Connect();
        Exec(con, sql);
    }

    private SqliteConnection Connect()
    {
        var con = new SqliteConnection($"Data Source={Path};Pooling=False");
        con.Open();
        return con;
    }

    private static void Exec(SqliteConnection con, string sql)
    {
        using var cmd = new SqliteCommand(sql, con);
        cmd.ExecuteNonQuery();
    }

    private static void Status(SqliteConnection con, string kind, string name) =>
        Exec(con, $"INSERT INTO derivation_status VALUES ('{kind}', '{name}', 'derived', '', '')");

    public void Dispose()
    {
        SqliteConnection.ClearAllPools();
        File.Delete(Path);
    }
}
