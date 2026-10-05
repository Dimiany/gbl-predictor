"""Fixture prediction: load a trained model and predict upcoming games.

Each prediction includes a point estimate (score and winner) PLUS a
confidence/uncertainty measure:

* One margin model drives both the win probability (Phi(margin / sigma))
  and the scoreline, so the two always agree on the winner.
* The margin model's walk-forward RMSE is returned as a "±" band around the
  predicted scoreline — a much more honest presentation than
  "Aris 83 Olympiacos 79" with no error bar.
"""

from __future__ import annotations

import difflib
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from src import config as cfg
from src.features import features_for_fixture, team_state_snapshot
from src.model import PredictorBundle, scoreline


@dataclass
class Fixture:
    """One upcoming game to predict."""

    date: str  # display date, e.g. "25/04/2026"
    matchday: str  # e.g. "Matchday 25"; empty string if unknown
    home: str
    away: str
    # Kickoff time in Athens local, 24h format "HH:MM". Empty string if
    # unknown (e.g. when hand-entering a fixture without a known tip-off).
    time: str = ""


@dataclass
class Prediction:
    """Prediction for one fixture."""

    date: str
    matchday: str
    home: str
    away: str
    predicted_home_score: int
    predicted_away_score: int
    predicted_margin: float  # unrounded margin, AFTER adjustments
    predicted_total: float  # unrounded total points
    home_win_probability: float  # Phi(margin / sigma), AFTER adjustments
    home_win_probability_raw: float  # same, BEFORE adjustments (for transparency)
    home_win_probability_elo: float  # plain Elo-implied probability (for comparison)
    score_uncertainty_pts: float  # ±pts band from the margin model's walk-forward RMSE
    winner: str  # the side with P(win) >= 50% — always matches the scoreline
    time: str = ""  # Kickoff "HH:MM" in Athens local, carried through from the Fixture
    model_version: str = ""  # cfg.MODEL_VERSION of the model that made this prediction
    # Manual adjustments applied to this fixture's predicted margin. 0.0 means
    # no adjustment. Positive values favor the home team; negative favor away.
    margin_adjustment_applied: float = 0.0
    # Human-readable list of the adjustments that fed into margin_adjustment_applied
    # — e.g. ["PAOK -4: star guard ACL"]. Empty when no adjustments were active.
    adjustment_notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Fixture loading from CSV
# ---------------------------------------------------------------------------

# Columns required in the fixtures CSV. Kept as module-level constants so
# error messages can reference the exact names a user should use.
FIXTURE_CSV_COLUMNS = ("fixture_date", "matchday", "home_team", "away_team")


def load_fixtures_from_csv(
    path: Path = cfg.UPCOMING_FIXTURES_CSV,
) -> tuple[list[Fixture], list[pd.Timestamp]]:
    """Read the upcoming fixtures CSV and return (fixtures, dates).

    The CSV must have columns: fixture_date, matchday, home_team, away_team.
    Rows where home_team or away_team is empty are silently skipped — that
    way a user can leave placeholder rows in the file without them blowing
    anything up.
    """
    df = pd.read_csv(path)

    # Fail early with a clear message if the user deleted or renamed a column.
    missing = [c for c in FIXTURE_CSV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Fixtures CSV at {path} is missing columns: {missing}. "
            f"Expected columns: {list(FIXTURE_CSV_COLUMNS)}"
        )

    # Drop any rows where a team name is missing. dropna on the two name
    # columns covers both empty strings (read as NaN) and genuinely blank rows.
    df = df.dropna(subset=["home_team", "away_team"]).copy()

    # Parse dates once up-front. dayfirst=True so "15/04/2026" is read as
    # 15 April (European) rather than the US mm/dd interpretation.
    df["fixture_date"] = pd.to_datetime(df["fixture_date"], dayfirst=True)

    # fixture_time is a newer column (added with the FlashScore integration).
    # Older CSVs won't have it — fall back to empty string so predictions
    # still work, they'll just lack kickoff times.
    has_time = "fixture_time" in df.columns

    fixtures: list[Fixture] = []
    dates: list[pd.Timestamp] = []
    for _, row in df.iterrows():
        # Normalize matchday: pandas reads empty CSV cells as NaN, and
        # ``str(NaN)`` literally produces "nan" — which would show as ugly
        # "nan" text in the UI. Coerce to empty string here.
        raw_matchday = row["matchday"]
        matchday = "" if pd.isna(raw_matchday) else str(raw_matchday).strip()

        raw_time = row["fixture_time"] if has_time else None
        time_str = "" if raw_time is None or pd.isna(raw_time) else str(raw_time).strip()

        fixtures.append(
            Fixture(
                # Full dd/mm/yyyy for display — consistent with the CSV format
                # the user edits.
                date=row["fixture_date"].strftime("%d/%m/%Y"),
                matchday=matchday,
                home=str(row["home_team"]).strip(),
                away=str(row["away_team"]).strip(),
                time=time_str,
            )
        )
        dates.append(row["fixture_date"])

    return fixtures, dates


def next_round(
    fixtures: list[Fixture],
    dates: list[pd.Timestamp],
    window_days: int = cfg.NEXT_ROUND_WINDOW_DAYS,
) -> tuple[list[Fixture], list[pd.Timestamp]]:
    """Keep only the next round: fixtures within ``window_days`` of the earliest one.

    upcoming_fixtures.csv holds the whole remaining season. Predicting games
    months ahead is noise (form and rest days are stale by then), so the UI
    and dashboard only score the round that's actually next.
    """
    if not fixtures:
        return [], []
    cutoff = min(dates) + pd.Timedelta(days=window_days)
    kept = [(f, d) for f, d in zip(fixtures, dates, strict=True) if d <= cutoff]
    return [f for f, _ in kept], [d for _, d in kept]


# ---------------------------------------------------------------------------
# Team-name validation
# ---------------------------------------------------------------------------


def known_teams_from_history(history: pd.DataFrame) -> set[str]:
    """Return the set of team names that appear in the history CSV."""
    # .unique() on a concat of both columns catches every team that has ever
    # played, home or away. Keeping them as-is preserves case / accents.
    return set(history[cfg.COL_HOME].unique()).union(history[cfg.COL_AWAY].unique())


def _suggest_correction(name: str, known: set[str]) -> str:
    """Return a short hint about the most likely intended team name.

    Uses difflib's fuzzy matching — the same algorithm git uses to suggest
    "did you mean this command?". Returns an empty string when nothing's
    close enough to be worth suggesting.
    """
    matches = difflib.get_close_matches(name, known, n=1, cutoff=0.6)
    if matches:
        return f" (did you mean {matches[0]!r}?)"
    return ""


def validate_team_names(fixtures: list[Fixture], history: pd.DataFrame) -> None:
    """Raise ValueError if any fixture references a team not in history.

    This guards against the silent-typo failure mode: if you write "PAO"
    instead of "Panathinaikos", the Elo / form lookups would treat it as a
    brand-new team (rating 1500, no form history) and quietly produce
    garbage predictions. Much better to refuse to predict and point at the
    likely fix.
    """
    known = known_teams_from_history(history)
    bad: list[str] = []
    for fx in fixtures:
        for role, name in (("home", fx.home), ("away", fx.away)):
            if name not in known:
                bad.append(f"{role}: {name!r}{_suggest_correction(name, known)}")

    if bad:
        # Sorting + deduplicating the error list makes the message stable
        # when multiple fixtures share the same typo.
        bad_unique = sorted(set(bad))
        raise ValueError(
            "Fixture references {n} unknown team name(s):\n  - {lines}\n"
            "Known teams: {known}".format(
                n=len(bad_unique),
                lines="\n  - ".join(bad_unique),
                known=", ".join(sorted(known)),
            )
        )


# ---------------------------------------------------------------------------
# Manual adjustments (injuries, suspensions, coach changes, …)
# ---------------------------------------------------------------------------
# The idea: the model can't know about off-court events. This CSV lets a
# human encode domain knowledge as a margin-point shift that applies while
# the adjustment is active. Example row:
#
#     team,          effective_date, expires_date, margin_adjustment, note
#     PAOK,          2026-04-18,     2026-04-25,   -4,                star guard ACL
#
# A NEGATIVE adjustment weakens the team. So if PAOK is home, the predicted
# margin (home - away) shifts DOWN by 4; if PAOK is away, it shifts UP by 4.
# ---------------------------------------------------------------------------

ADJUSTMENT_COLUMNS = (
    "team",
    "effective_date",
    "expires_date",
    "margin_adjustment",
    "note",
)


def load_adjustments(path: Path = cfg.ADJUSTMENTS_CSV) -> pd.DataFrame:
    """Read the adjustments CSV. Returns an empty DataFrame if file is missing.

    A missing or empty adjustments file is normal — most weeks you won't
    have any active adjustments. We do NOT treat that as an error.
    """
    # File doesn't exist: caller probably hasn't created it yet. Graceful return.
    if not path.exists():
        return pd.DataFrame(columns=list(ADJUSTMENT_COLUMNS))

    df = pd.read_csv(path)

    # Empty file with only a header row → also fine, nothing active.
    if df.empty:
        return df

    # Schema check: the column set must match, otherwise fail loudly so the
    # user fixes the file instead of silently getting unadjusted predictions.
    missing = [c for c in ADJUSTMENT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Adjustments CSV at {path} is missing columns: {missing}. "
            f"Expected columns: {list(ADJUSTMENT_COLUMNS)}"
        )

    # Parse dates. dayfirst=True for European dd/mm/yyyy input.
    # expires_date is optional (blank = never expires); we fill NaT with a
    # far-future date so the "is active?" comparison is simple.
    df["effective_date"] = pd.to_datetime(df["effective_date"], dayfirst=True)
    df["expires_date"] = pd.to_datetime(
        df["expires_date"],
        dayfirst=True,
    ).fillna(pd.Timestamp("2999-12-31"))
    # Numeric conversion — catches typos like "four" early rather than
    # silently coercing to NaN mid-pipeline.
    df["margin_adjustment"] = pd.to_numeric(df["margin_adjustment"], errors="raise")
    return df


# ---------------------------------------------------------------------------
# Rosters + absences (the tier-based injury-tracking layer)
# ---------------------------------------------------------------------------
# Two files instead of one:
#   rosters.csv   — slow-changing: who plays for each team and how important
#                   they are (tier in {star, starter, rotation, bench}).
#   absences.csv  — fast-changing: who is out, from when until when, and why.
#
# At predict time we combine them: for each active absence, we look up the
# player's tier in rosters, translate the tier to a point-swing via
# cfg.PLAYER_TIER_POINTS, and produce the same shape as adjustments.csv.
# The advantage over a single "margin_adjustment" column is that you tune
# TIER VALUES once (in config) and never again — mark a player as "starter"
# and their absence is worth the same every time they get hurt.
# ---------------------------------------------------------------------------

ROSTER_COLUMNS = ("team", "player", "tier", "note")
ABSENCE_COLUMNS = (
    "team",
    "player",
    "effective_date",
    "expires_date",
    "reason",
)


def load_rosters(path: Path = cfg.ROSTERS_CSV) -> pd.DataFrame:
    """Read the rosters CSV. Returns empty DataFrame if file is missing."""
    if not path.exists():
        return pd.DataFrame(columns=list(ROSTER_COLUMNS))
    df = pd.read_csv(path)
    if df.empty:
        return df

    missing = [c for c in ROSTER_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Rosters CSV at {path} is missing columns: {missing}. "
            f"Expected columns: {list(ROSTER_COLUMNS)}"
        )

    # Drop rows where player is blank — the CSV ships as a template with one
    # "team header" row per team so the user can see every team's exact
    # spelling at a glance. Those stub rows are meant to be ignored until
    # someone actually fills in a player name.
    df = df.dropna(subset=["player"]).copy()
    df = df[df["player"].astype(str).str.strip() != ""]

    # Reject unknown tiers up front — a typo like "starer" would silently
    # fall back to "rotation" otherwise. Better to fail with a clear message.
    bad_tiers = set(df["tier"].dropna().unique()) - set(cfg.PLAYER_TIER_POINTS)
    if bad_tiers:
        raise ValueError(
            f"Rosters CSV has unknown tier(s): {sorted(bad_tiers)}. "
            f"Allowed tiers: {sorted(cfg.PLAYER_TIER_POINTS)}."
        )
    return df


def load_absences(path: Path = cfg.ABSENCES_CSV) -> pd.DataFrame:
    """Read the absences CSV. Returns empty DataFrame if file is missing."""
    if not path.exists():
        return pd.DataFrame(columns=list(ABSENCE_COLUMNS))
    df = pd.read_csv(path)
    if df.empty:
        return df

    missing = [c for c in ABSENCE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Absences CSV at {path} is missing columns: {missing}. "
            f"Expected columns: {list(ABSENCE_COLUMNS)}"
        )

    # dayfirst=True so "15/04/2026" reads as 15 April (European convention).
    df["effective_date"] = pd.to_datetime(df["effective_date"], dayfirst=True)
    df["expires_date"] = pd.to_datetime(
        df["expires_date"],
        dayfirst=True,
    ).fillna(pd.Timestamp("2999-12-31"))
    return df


def _tier_points(player: str, team: str, rosters: pd.DataFrame) -> tuple[float, str]:
    """Resolve a (team, player) to their (points, tier) from the rosters file.

    Returns cfg.DEFAULT_PLAYER_TIER's points if the player isn't listed —
    the safer default is "minor impact" rather than zero, so an absence you
    haven't characterised yet still has *some* effect. Callers can show a
    "please add this player to rosters.csv" nudge if they care.
    """
    if not rosters.empty:
        # Exact match on both team and player. Case-sensitive by design —
        # "Moustapha Fall" and "moustapha fall" are NOT the same row.
        hit = rosters[(rosters["team"] == team) & (rosters["player"] == player)]
        if not hit.empty:
            tier = hit.iloc[0]["tier"]
            return cfg.PLAYER_TIER_POINTS[tier], tier
    # Fallback path — player not in rosters.
    return cfg.PLAYER_TIER_POINTS[cfg.DEFAULT_PLAYER_TIER], cfg.DEFAULT_PLAYER_TIER


def absences_to_adjustments(
    absences: pd.DataFrame,
    rosters: pd.DataFrame,
) -> pd.DataFrame:
    """Translate an absences DataFrame into the same shape as adjustments.csv.

    One absence row becomes one adjustment row, with margin_adjustment
    derived from the player's tier in rosters (or the default tier if
    they're not listed). The resulting DataFrame can be concatenated with
    the manual-adjustments DataFrame and treated identically by the rest
    of the pipeline.
    """
    if absences.empty:
        # Return empty with matching schema so concat below is trivial.
        return pd.DataFrame(
            columns=[
                "team",
                "effective_date",
                "expires_date",
                "margin_adjustment",
                "note",
            ]
        )

    rows: list[dict] = []
    for _, a in absences.iterrows():
        points, tier = _tier_points(a["player"], a["team"], rosters)
        # Human-readable note — shows up in the HTML card and the DataFrame.
        # Includes tier so the user sees WHY the number is what it is.
        note = f"{a['player']} ({tier})"
        if pd.notna(a.get("reason", None)) and str(a["reason"]).strip():
            note += f" - {a['reason']}"
        rows.append(
            {
                "team": a["team"],
                "effective_date": a["effective_date"],
                "expires_date": a["expires_date"],
                "margin_adjustment": points,
                "note": note,
            }
        )
    return pd.DataFrame(rows)


def _team_adjustment_on(
    date: pd.Timestamp,
    team: str,
    adjustments: pd.DataFrame,
) -> tuple[float, list[str]]:
    """Return (total_points_shift, notes) for ``team`` on ``date``.

    Multiple active adjustments are summed — e.g. "star guard out (-3)"
    plus "coach fired (-2)" = -5 total.
    """
    if adjustments.empty:
        return 0.0, []
    # Filter to rows where team matches AND the fixture date falls in the
    # effective window. Inclusive on both ends (a same-day effective_date
    # applies; a same-day expires_date still applies).
    mask = (
        (adjustments["team"] == team)
        & (adjustments["effective_date"] <= date)
        & (adjustments["expires_date"] >= date)
    )
    active = adjustments[mask]
    if active.empty:
        return 0.0, []
    total = float(active["margin_adjustment"].sum())
    # Build the explanatory strings that end up in the HTML card / DataFrame.
    notes = [
        f"{row['team']} {row['margin_adjustment']:+g}: {row['note']}"
        for _, row in active.iterrows()
    ]
    return total, notes


def _normal_cdf(z: float) -> float:
    """Cumulative distribution function of the standard normal — no scipy required.

    We use this to convert a margin shift into a win-probability shift:
    if the model's predicted margin moves by ΔM points, the implied change
    in P(home win) is roughly Φ((μ+ΔM)/σ) - Φ(μ/σ), where σ is the margin RMSE.
    """
    # math.erf gives the error function; the normal CDF is (1 + erf(z/√2)) / 2.
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _adjusted_win_prob(
    base_prob: float,
    predicted_margin: float,
    margin_shift: float,
    sigma: float,
) -> float:
    """Shift a win probability by the margin-implied probability delta.

    Why not just re-run the classifier? Because the classifier doesn't see
    the adjustment. Instead, we compute how much a margin-based model WOULD
    have shifted its probability and apply the same delta to the ensemble
    probability. Preserves what the classifier already knows about
    form/Elo/H2H, adjusts for the new margin belief.
    """
    if margin_shift == 0.0 or sigma <= 0.0:
        return base_prob
    # Margin-based implied win prob before and after the shift.
    p_before = _normal_cdf(predicted_margin / sigma)
    p_after = _normal_cdf((predicted_margin + margin_shift) / sigma)
    # Apply the delta and clip — tiny floating-point drift can push the
    # result just past 0 or 1, which would then look wrong in the UI.
    return float(max(0.0, min(1.0, base_prob + (p_after - p_before))))


def predict_fixtures(
    fixtures: list[Fixture],
    fixture_dates: list[pd.Timestamp] | None = None,
    history: pd.DataFrame | None = None,
    bundle: PredictorBundle | None = None,
    adjustments: pd.DataFrame | None = None,
) -> list[Prediction]:
    """Predict a batch of upcoming fixtures.

    Parameters
    ----------
    fixtures
        The games to predict, in any order.
    fixture_dates
        Actual datetimes of the fixtures (needed for rest-days feature).
        Must be the same length as ``fixtures``. If omitted, we use "today"
        for all of them — fine for a quick demo, less accurate in practice.
    history
        The completed games used to compute Elo, form, etc. Defaults to the
        raw CSV on disk.
    bundle
        Pre-loaded trained model. If omitted, we load the one saved by
        ``train_and_save``.
    adjustments
        Manual margin adjustments (for injuries / etc.). Defaults to the
        contents of ``data/raw/adjustments.csv`` (or none, if that file is
        missing or empty).
    """
    if bundle is None:
        bundle = PredictorBundle.load()

    # Empty input → empty output. Without this guard, the downstream
    # ``pd.DataFrame([])[bundle.feature_cols]`` blows up with a KeyError
    # because there are no columns to select from.
    if not fixtures:
        return []

    if history is None:
        history = pd.read_csv(cfg.RAW_GAMES_CSV)

    # Absences + rosters layer: translate "Fall is out" into the same
    # adjustment-row shape as the manual adjustments.csv, then merge them.
    # This keeps the downstream code unchanged — everything downstream still
    # sees a single adjustments DataFrame, regardless of where the rows came from.
    rosters = load_rosters()
    absences = load_absences()
    absence_adjustments = absences_to_adjustments(absences, rosters)

    if adjustments is None:
        adjustments = load_adjustments()

    # Combine manual adjustments with absence-derived ones. If both files
    # are empty we still end up with a valid (empty) DataFrame.
    adjustments = pd.concat(
        [adjustments, absence_adjustments],
        ignore_index=True,
        sort=False,
    )

    # Guard against silent typos in fixture team names: we'd rather refuse
    # to predict than return nonsense with a neutral-rated stand-in team.
    validate_team_names(fixtures, history)

    # Build per-team current state from all historical games. This is the
    # "memory" the model uses to size up each matchup.
    states, h2h = team_state_snapshot(history)

    # Default fixture dates: if the caller didn't give us real ones, use now.
    # The rest-days feature will still be approximately right.
    if fixture_dates is None:
        now = pd.Timestamp.now().normalize()
        fixture_dates = [now] * len(fixtures)
    if len(fixture_dates) != len(fixtures):
        raise ValueError("fixture_dates must have the same length as fixtures")

    feature_rows = [
        features_for_fixture(f.home, f.away, d, states, h2h)
        for f, d in zip(fixtures, fixture_dates, strict=True)
    ]
    X = pd.DataFrame(feature_rows)
    margins, totals, win_probs = bundle.predict(X)
    # Plain Elo probability, shown next to the model's for comparison.
    win_probs_elo = X["home_win_prob_elo"].to_numpy()

    # The ±band on the scoreline: how far off the margin model typically was
    # in the walk-forward evaluation.
    margin_rmse = bundle.metrics.get("margin_rmse", bundle.margin_sigma)

    results: list[Prediction] = []
    for fixture, fixture_date, p_win, p_elo, margin, total in zip(
        fixtures,
        fixture_dates,
        win_probs,
        win_probs_elo,
        margins,
        totals,
        strict=True,
    ):
        # Look up manual adjustments active on this fixture date. A negative
        # number weakens the team — so the net margin shift is:
        #     net = home_adjustment - away_adjustment
        # If PAOK (home) is -4, net = -4 (home is expected to lose 4 more).
        # If PAOK (away) is -4, net = +4 (margin moves toward the home side).
        home_adj, home_notes = _team_adjustment_on(fixture_date, fixture.home, adjustments)
        away_adj, away_notes = _team_adjustment_on(fixture_date, fixture.away, adjustments)
        margin_shift = home_adj - away_adj

        # Apply the shift to the margin; total points is left alone — an
        # injury usually changes WHO scores more, not how many points get
        # scored overall. This is a reasonable first-order model.
        adjusted_margin = float(margin) + margin_shift
        # Same Phi(margin / sigma) mapping as the model, so probability and
        # scoreline stay in agreement after the shift too.
        adjusted_p_win = _adjusted_win_prob(
            base_prob=float(p_win),
            predicted_margin=float(margin),
            margin_shift=margin_shift,
            sigma=bundle.margin_sigma,
        )
        home_score, away_score = scoreline(adjusted_margin, float(total))

        results.append(
            Prediction(
                date=fixture.date,
                matchday=fixture.matchday,
                home=fixture.home,
                away=fixture.away,
                predicted_home_score=home_score,
                predicted_away_score=away_score,
                predicted_margin=adjusted_margin,
                predicted_total=float(total),
                home_win_probability=adjusted_p_win,
                home_win_probability_raw=float(p_win),
                home_win_probability_elo=float(p_elo),
                score_uncertainty_pts=float(margin_rmse),
                winner=fixture.home if adjusted_margin >= 0 else fixture.away,
                margin_adjustment_applied=margin_shift,
                adjustment_notes=home_notes + away_notes,
                time=fixture.time,
                model_version=bundle.version,
            )
        )

    return results


def predictions_to_dataframe(preds: list[Prediction]) -> pd.DataFrame:
    """Convenience: turn a list of Prediction objects into a tidy DataFrame."""
    return pd.DataFrame([p.as_dict() for p in preds])
