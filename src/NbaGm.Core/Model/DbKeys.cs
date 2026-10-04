using System.Text;

namespace NbaGm.Core.Model;

/// <summary>
/// Maps enum members to the snake_case keys the pipeline writes (e.g.
/// <c>OffensiveIq</c> ↔ <c>offensive_iq</c>), so the two sides share one naming rule.
/// </summary>
public static class DbKeys
{
    public static string ToKey<TEnum>(TEnum value) where TEnum : struct, Enum => ToSnakeCase(value.ToString());

    public static bool TryParse<TEnum>(string key, out TEnum value) where TEnum : struct, Enum
    {
        foreach (var candidate in Enum.GetValues<TEnum>())
        {
            if (ToKey(candidate) == key)
            {
                value = candidate;
                return true;
            }
        }
        value = default;
        return false;
    }

    public static string ToSnakeCase(string pascal)
    {
        var sb = new StringBuilder(pascal.Length + 8);
        for (var i = 0; i < pascal.Length; i++)
        {
            var c = pascal[i];
            if (char.IsUpper(c) && i > 0)
            {
                sb.Append('_');
            }
            sb.Append(char.ToLowerInvariant(c));
        }
        return sb.ToString();
    }
}
