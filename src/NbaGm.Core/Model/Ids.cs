namespace NbaGm.Core.Model;

/// <summary>The 27 rated attributes locked in doc 01 (measurables live in <see cref="Measurables"/>).</summary>
public enum AttributeId
{
    // Offense: rim scoring
    DrivingLayup,
    DrivingDunk,
    StandingDunk,
    Touch,
    PostScoring,

    // Offense: shooting
    ThreePointer,
    MidRange,
    FreeThrow,

    // Offense: playmaking
    BallHandle,
    PassingAccuracy,
    Vision,
    OffensiveIq,

    // Defense
    OffensiveRebounding,
    DefensiveRebounding,
    Steals,
    ShotBlocking,
    OffBallDefense,
    OnBallDefense,
    PostDefense,
    RimProtection,
    DefensiveIq,

    // Physicals
    Speed,
    Acceleration,
    LateralQuickness,
    Vertical,
    Strength,
    Stamina,
}

/// <summary>
/// The 20 Phase 1 tendencies (doc 03), each a real rate in [0, 1]. Either/or pairs are one
/// slider; each pair's comment says which option 1.0 means.
/// </summary>
public enum TendencyId
{
    ThreePointAttemptRate,
    MidRangeAttemptRate,
    RimAttemptRate,
    /// <summary>Pull-up share of catch-and-shoot + pull-up attempts (1 = all pull-up).</summary>
    CatchAndShootVsPullUp,
    ShotClockUsage,

    IsolationFrequency,
    PostUpFrequency,
    PickAndRollUsage,
    /// <summary>Kick-out share of drive passes + drive shots (1 = always kicks).</summary>
    DriveAndKickVsDriveToFinish,
    /// <summary>Passes made / (passes made + FGA) (1 = pass-first).</summary>
    PassFirstVsScoreFirst,
    /// <summary>FTA / (FGA + FTA).</summary>
    FoulContactSeeking,

    CuttingFrequency,
    ScreenSettingWillingness,

    GambleForSteals,
    DefensiveFoulAggression,

    OffensiveReboundCrashRate,
    /// <summary>Box-out rate (1 = always boxes out; leak-out is the complement).</summary>
    BoxOutVsLeakOut,
    FastBreakLeakOut,
    LooseBallWillingness,
    ChargeTakingWillingness,
}

/// <summary>The five locked traits (doc 04).</summary>
public enum TraitId
{
    Durability,
    Consistency,
    Clutch,
    Hustle,
    Streaky,
}
