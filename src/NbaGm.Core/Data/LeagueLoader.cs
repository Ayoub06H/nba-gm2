using System.Globalization;
using Microsoft.Data.Sqlite;
using NbaGm.Core.Model;

namespace NbaGm.Core.Data;

public sealed class IncompleteLeagueDataException(CompletenessReport report)
    : Exception("League file does not meet Phase 1's definition of done:\n" + report)
{
    public CompletenessReport Report { get; } = report;
}

/// <summary>
/// Loads the league from the SQLite file written by pipeline/build.py. Local file only,
/// no network. Refuses to load a file in which any player lacks a derived value: the
/// game never runs on placeholders.
/// </summary>
public static class LeagueLoader
{
    public static League Load(string path)
    {
        var report = CompletenessReport.Read(path);
        if (!report.IsPhase1Complete)
        {
            throw new IncompleteLeagueDataException(report);
        }

        using var con = Open(path);
        var attributes = ReadMap(con, "SELECT player_id, attribute, rating FROM player_attributes",
            r => r.GetDouble(2), (string k, out AttributeId id) => DbKeys.TryParse(k, out id));
        var tendencies = ReadMap(con, "SELECT player_id, tendency, value FROM player_tendencies",
            r => r.GetDouble(2), (string k, out TendencyId id) => DbKeys.TryParse(k, out id));
        var traits = ReadMap(con, "SELECT player_id, trait, value, z_score, tier, tier_name FROM player_traits",
            r => new Trait(r.GetDouble(2), r.GetDouble(3), r.GetInt32(4), r.IsDBNull(5) ? null : r.GetString(5)),
            (string k, out TraitId id) => DbKeys.TryParse(k, out id));
        var contracts = new Dictionary<int, Contract>();
        using (var cmd = new SqliteCommand("SELECT player_id, salary, years_remaining FROM contracts", con))
        using (var r = cmd.ExecuteReader())
        {
            while (r.Read())
            {
                contracts[r.GetInt32(0)] = new Contract(r.GetDouble(1), r.GetInt32(2));
            }
        }

        var rosters = new Dictionary<int, List<Player>>();
        using (var cmd = new SqliteCommand(
            "SELECT player_id, team_id, first_name, last_name, jersey, listed_position, position, " +
            "height_in, weight_lb, wingspan_in, wingspan_imputed, games_played, games_started, " +
            "minutes_per_game, depth_rank FROM players ORDER BY team_id, depth_rank", con))
        using (var r = cmd.ExecuteReader())
        {
            while (r.Read())
            {
                var id = r.GetInt32(0);
                var player = new Player
                {
                    Id = id,
                    TeamId = r.GetInt32(1),
                    FirstName = r.GetString(2),
                    LastName = r.GetString(3),
                    Jersey = r.IsDBNull(4) ? null : r.GetString(4),
                    ListedPosition = r.IsDBNull(5) ? null : r.GetString(5),
                    Position = r.IsDBNull(6) ? null : Enum.Parse<Position>(r.GetString(6)),
                    Measurables = new Measurables(r.GetDouble(7), r.GetDouble(8), r.GetDouble(9), r.GetInt32(10) != 0),
                    Usage = new SeasonUsage(r.GetInt32(11), r.GetInt32(12), r.GetDouble(13), r.GetInt32(14)),
                    Attributes = new AttributeSet(attributes[id]),
                    Tendencies = new TendencySet(tendencies[id]),
                    Traits = new TraitSet(traits[id]),
                    Contract = contracts.GetValueOrDefault(id),
                };
                if (!rosters.TryGetValue(player.TeamId, out var list))
                {
                    rosters[player.TeamId] = list = [];
                }
                list.Add(player);
            }
        }

        var teams = new List<Team>();
        using (var cmd = new SqliteCommand("SELECT team_id, abbreviation, city, name FROM teams ORDER BY team_id", con))
        using (var r = cmd.ExecuteReader())
        {
            while (r.Read())
            {
                var id = r.GetInt32(0);
                teams.Add(new Team
                {
                    Id = id,
                    Abbreviation = r.GetString(1),
                    City = r.GetString(2),
                    Name = r.GetString(3),
                    Roster = rosters.GetValueOrDefault(id) ?? [],
                });
            }
        }

        var games = new List<Game>();
        using (var cmd = new SqliteCommand(
            "SELECT game_id, game_date, home_team_id, away_team_id, home_points, away_points FROM games " +
            "ORDER BY game_date, game_id", con))
        using (var r = cmd.ExecuteReader())
        {
            while (r.Read())
            {
                games.Add(new Game(r.GetString(0), ParseDate(r.GetString(1)), r.GetInt32(2), r.GetInt32(3),
                    r.IsDBNull(4) ? null : r.GetInt32(4), r.IsDBNull(5) ? null : r.GetInt32(5)));
            }
        }

        return new League { Season = report.Season, Teams = teams, Schedule = games };
    }

    internal static SqliteConnection Open(string path)
    {
        if (!File.Exists(path))
        {
            throw new FileNotFoundException("League database not found", path);
        }
        var con = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = path,
            Mode = SqliteOpenMode.ReadOnly,
        }.ToString());
        con.Open();
        return con;
    }

    private delegate bool KeyParser<TEnum>(string key, out TEnum id);

    private static Dictionary<int, Dictionary<TEnum, TValue>> ReadMap<TEnum, TValue>(
        SqliteConnection con, string sql, Func<SqliteDataReader, TValue> value, KeyParser<TEnum> parse)
        where TEnum : struct, Enum
    {
        var map = new Dictionary<int, Dictionary<TEnum, TValue>>();
        using var cmd = new SqliteCommand(sql, con);
        using var r = cmd.ExecuteReader();
        while (r.Read())
        {
            if (!parse(r.GetString(1), out var id))
            {
                throw new InvalidDataException($"unknown key '{r.GetString(1)}' for {typeof(TEnum).Name}");
            }
            var pid = r.GetInt32(0);
            if (!map.TryGetValue(pid, out var inner))
            {
                map[pid] = inner = new Dictionary<TEnum, TValue>();
            }
            inner[id] = value(r);
        }
        return map;
    }

    private static DateOnly ParseDate(string s)
    {
        string[] formats = ["yyyy-MM-dd", "yyyy-MM-ddTHH:mm:ss", "MMM dd, yyyy"];
        return DateOnly.FromDateTime(DateTime.ParseExact(s, formats, CultureInfo.InvariantCulture,
            DateTimeStyles.AllowWhiteSpaces));
    }
}
