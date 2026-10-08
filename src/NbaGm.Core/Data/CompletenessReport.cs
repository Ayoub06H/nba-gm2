using System.Text;
using Microsoft.Data.Sqlite;
using NbaGm.Core.Model;

namespace NbaGm.Core.Data;

/// <summary>How many rostered players have a real derived value for one field.</summary>
public sealed record FieldCompleteness(
    string Kind,
    string Key,
    int PlayersWithValue,
    int TotalPlayers,
    string Status,
    string Note)
{
    public bool IsComplete => TotalPlayers > 0 && PlayersWithValue == TotalPlayers;
}

/// <summary>
/// Phase 1's definition of done (doc 11), checked against a league file: all 30 teams, and
/// every rostered player with a value for every attribute, tendency, trait and measurable
/// (players with no exposure carry doc 02's flagged placeholder). Reads the file without
/// loading the model, so it works on incomplete files too.
/// </summary>
public sealed class CompletenessReport
{
    public required string Season { get; init; }
    public required int TeamCount { get; init; }
    public required int PlayerCount { get; init; }

    /// <summary>Rostered players with no 2025-26 exposure (placeholder ratings, doc 02).</summary>
    public required int NoDataPlayers { get; init; }
    public required IReadOnlyList<FieldCompleteness> Fields { get; init; }

    /// <summary>Fields doc 11 allows to stay empty (contracts without a named real source).</summary>
    public required IReadOnlyList<FieldCompleteness> OtherFields { get; init; }

    /// <summary>Keys present in the file that the C# model does not know, or vice versa.</summary>
    public required IReadOnlyList<string> KeyMismatches { get; init; }

    public bool IsPhase1Complete =>
        TeamCount == 30 && PlayerCount > 0 && KeyMismatches.Count == 0 && Fields.All(f => f.IsComplete);

    public static CompletenessReport Read(string path)
    {
        using var con = LeagueLoader.Open(path);
        int Scalar(string sql) => Convert.ToInt32(new SqliteCommand(sql, con).ExecuteScalar());

        var players = Scalar("SELECT COUNT(*) FROM players");
        var status = new Dictionary<(string, string), (string Status, string Note)>();
        using (var cmd = new SqliteCommand("SELECT kind, name, status, note FROM derivation_status", con))
        using (var r = cmd.ExecuteReader())
        {
            while (r.Read())
            {
                status[(r.GetString(0), r.GetString(1))] = (r.GetString(2), r.IsDBNull(3) ? "" : r.GetString(3));
            }
        }

        var mismatches = new List<string>();
        var fields = new List<FieldCompleteness>();

        FieldCompleteness Field(string kind, string key, string countSql)
        {
            var s = status.TryGetValue((kind, key), out var st) ? st : ("missing", "");
            if (s.Item1 == "missing")
            {
                mismatches.Add($"{kind} '{key}' has no derivation_status row");
            }
            return new FieldCompleteness(kind, key, Scalar(countSql), players, s.Item1, s.Item2);
        }

        void Fields<TEnum>(string kind, string table, string column, string valueCondition)
            where TEnum : struct, Enum
        {
            foreach (var id in Enum.GetValues<TEnum>())
            {
                var key = DbKeys.ToKey(id);
                fields.Add(Field(kind, key,
                    $"SELECT COUNT(*) FROM {table} t JOIN players p USING (player_id) " +
                    $"WHERE t.{column} = '{key}' AND {valueCondition}"));
            }
            using var cmd = new SqliteCommand($"SELECT DISTINCT {column} FROM {table}", con);
            using var r = cmd.ExecuteReader();
            while (r.Read())
            {
                if (!DbKeys.TryParse<TEnum>(r.GetString(0), out _))
                {
                    mismatches.Add($"{kind} '{r.GetString(0)}' in {table} is not in the C# model");
                }
            }
        }

        Fields<AttributeId>("attribute", "player_attributes", "attribute", "t.rating IS NOT NULL");
        Fields<TendencyId>("tendency", "player_tendencies", "tendency", "t.value IS NOT NULL");
        // A player with no data has no trait value, only z = 0 / tier 0 ("no trait").
        Fields<TraitId>("trait", "player_traits", "trait",
            "t.z_score IS NOT NULL AND t.tier IS NOT NULL AND (t.value IS NOT NULL OR p.no_data = 1)");
        foreach (var col in new[] { "height_in", "weight_lb", "wingspan_in" })
        {
            fields.Add(Field("measurable", col, $"SELECT COUNT(*) FROM players WHERE {col} IS NOT NULL"));
        }

        fields.Add(Field("player_field", "position", "SELECT COUNT(*) FROM players WHERE position IS NOT NULL"));
        var other = new List<FieldCompleteness>
        {
            Field("player_field", "contract",
                "SELECT COUNT(*) FROM players p WHERE EXISTS (SELECT 1 FROM contracts c WHERE c.player_id = p.player_id)"),
        };

        var season = new SqliteCommand("SELECT value FROM meta WHERE key = 'season'", con).ExecuteScalar() as string;
        return new CompletenessReport
        {
            Season = season ?? "?",
            TeamCount = Scalar("SELECT COUNT(DISTINCT team_id) FROM players"),
            PlayerCount = players,
            NoDataPlayers = Scalar("SELECT COUNT(*) FROM players WHERE no_data = 1"),
            Fields = fields,
            OtherFields = other,
            KeyMismatches = mismatches,
        };
    }

    public override string ToString()
    {
        var sb = new StringBuilder();
        sb.AppendLine($"Season {Season}: {PlayerCount} rostered players on {TeamCount} teams " +
                      $"({NoDataPlayers} with no data: placeholder ratings)");
        foreach (var group in Fields.GroupBy(f => f.Kind))
        {
            var done = group.Count(f => f.IsComplete);
            sb.AppendLine($"  {group.Key} fields: {done}/{group.Count()} complete for every player");
        }
        var incomplete = Fields.Concat(OtherFields).Where(f => !f.IsComplete).ToList();
        if (incomplete.Count > 0)
        {
            sb.AppendLine("  Incomplete:");
            foreach (var f in incomplete)
            {
                sb.AppendLine($"    {f.Kind,-12} {f.Key,-36} {f.PlayersWithValue,4}/{f.TotalPlayers,-4} " +
                              $"{f.Status,-8} {f.Note}");
            }
        }
        foreach (var m in KeyMismatches)
        {
            sb.AppendLine($"  KEY MISMATCH: {m}");
        }
        sb.AppendLine(IsPhase1Complete ? "PHASE 1 COMPLETE" : "PHASE 1 NOT COMPLETE");
        return sb.ToString();
    }
}
