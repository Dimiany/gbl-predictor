"""HTML rendering for the notebook UI.

Two public renderers — both return a single self-contained <div> you can
drop into any Jupyter cell via ``IPython.display.HTML``:

  * ``render_fixtures_table_html``   — the pre-prediction view (list only)
  * ``render_predictions_html``      — the post-prediction view (cards)

Design notes: system font stack, muted palette, minimal borders. The
per-fixture uncertainty (±pts) is shown ONCE in the footer instead of
repeating on every card — it's the same number everywhere, so showing
it twelve times is noise.
"""

from __future__ import annotations

import pandas as pd

from src.predict import Fixture, Prediction

# A single font stack reused across both renderers — the best native-looking
# font on whatever OS the user is on. No web fonts = no network dependency.
_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

_OUTER_STYLE = (
    f"background:#0f0f14;border-radius:14px;padding:24px 28px;font-family:{_FONT};color:#e7e7ea;"
)


def _confidence_label(prob: float) -> str:
    if prob >= 0.75:
        return "Strong home"
    if prob >= 0.60:
        return "Lean home"
    if prob >= 0.40:
        return "Toss-up"
    if prob >= 0.25:
        return "Lean away"
    return "Strong away"


def _when_cell(date: str, time: str) -> str:
    """Render the 'when' (date + optional time) for one fixture row."""
    return date + (f" &middot; {time}" if time else "")


# ---------------------------------------------------------------------------
# Pre-prediction fixtures table
# ---------------------------------------------------------------------------


def render_fixtures_table_html(
    fixtures: list[Fixture],
    season_label: str = "GBL 2025/26",
) -> str:
    if not fixtures:
        return (
            f"<div style='{_OUTER_STYLE}'>"
            "<div style='font-size:16px;font-weight:600;margin-bottom:8px;'>"
            f"{season_label} &mdash; Upcoming Fixtures</div>"
            "<p style='color:#9aa0a6;margin:0;font-size:13px;line-height:1.5;'>"
            "No upcoming fixtures right now. The next matchday will appear here "
            "automatically once it's published.</p></div>"
        )

    rows = "\n".join(
        f"""<tr style="border-bottom:1px solid #22232a;">
          <td style="padding:12px 14px;color:#9aa0a6;font-size:12px;white-space:nowrap;">{_when_cell(f.date, f.time)}</td>
          <td style="padding:12px 14px;text-align:right;font-size:14px;">{f.home}</td>
          <td style="padding:12px 4px;color:#5f6368;font-size:11px;">vs</td>
          <td style="padding:12px 14px;text-align:left;font-size:14px;">{f.away}</td>
        </tr>"""
        for f in fixtures
    )

    return f"""
    <div style="{_OUTER_STYLE}">
      <div style="font-size:16px;font-weight:600;margin-bottom:12px;letter-spacing:.2px;">
        {season_label} &mdash; Upcoming Fixtures
      </div>
      <table style="width:100%;border-collapse:collapse;">
        <thead>
          <tr style="color:#6b7280;font-size:10px;text-transform:uppercase;letter-spacing:1.3px;">
            <th style="padding:8px 14px;text-align:left;font-weight:500;">When</th>
            <th style="padding:8px 14px;text-align:right;font-weight:500;">Home</th>
            <th></th>
            <th style="padding:8px 14px;text-align:left;font-weight:500;">Away</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    """


# ---------------------------------------------------------------------------
# Post-prediction cards
# ---------------------------------------------------------------------------


def render_predictions_html(
    preds: list[Prediction],
    season_label: str = "GBL 2025/26",
) -> str:
    if not preds:
        return (
            f"<div style='{_OUTER_STYLE}'>"
            "<p style='color:#888;margin:0;'>No predictions to show.</p></div>"
        )

    # All predictions share the same uncertainty (it's the model's test-set RMSE).
    # Show it once in the footer rather than repeating on every card.
    shared_uncertainty = preds[0].score_uncertainty_pts

    cards: list[str] = []
    for p in preds:
        home_is_winner = p.winner == p.home
        home_color = "#ffd166" if home_is_winner else "#9aa0a6"
        away_color = "#ffd166" if not home_is_winner else "#9aa0a6"
        home_weight = 700 if home_is_winner else 500
        away_weight = 700 if not home_is_winner else 500

        prob_pct = round(p.home_win_probability * 100)
        confidence = _confidence_label(p.home_win_probability)

        # Empty matchday -> just show when. Empty time -> just date.
        # No more "nan" text anywhere.
        when = _when_cell(p.date, p.time)

        adjustment_html = ""
        if p.adjustment_notes:
            adjustment_html = (
                f'<div style="margin-top:8px;color:#f6c667;font-size:11px;">'
                f"Adjusted: {'; '.join(p.adjustment_notes)}</div>"
            )

        cards.append(f"""
        <div style="background:#171820;border-radius:10px;padding:14px 18px;margin-bottom:8px;">
          <div style="display:flex;align-items:center;gap:18px;">
            <div style="color:#9aa0a6;font-size:11px;width:130px;line-height:1.5;">
              {when}<br><span style="color:#5f6368;">{confidence}</span>
            </div>
            <div style="flex:1;text-align:right;color:{home_color};font-weight:{home_weight};font-size:14px;">
              {p.home}
            </div>
            <div style="min-width:96px;text-align:center;">
              <div style="font-size:22px;font-weight:700;letter-spacing:.5px;">
                {p.predicted_home_score} <span style="color:#5f6368;">&ndash;</span> {p.predicted_away_score}
              </div>
              <div style="color:#e7e7ea;font-size:13px;font-weight:600;margin-top:4px;letter-spacing:.3px;">
                Total: <span style="color:#ffd166;">{p.predicted_home_score + p.predicted_away_score}</span> pts
              </div>
            </div>
            <div style="flex:1;color:{away_color};font-weight:{away_weight};font-size:14px;">
              {p.away}
            </div>
            <div style="width:64px;text-align:right;color:#cdd0d4;font-size:12px;font-variant-numeric:tabular-nums;">
              {prob_pct}%
            </div>
          </div>
          <div style="margin-top:10px;background:#22232a;height:4px;border-radius:2px;overflow:hidden;">
            <div style="width:{prob_pct}%;background:linear-gradient(90deg,#00d084,#ffd166);height:100%;"></div>
          </div>
          {adjustment_html}
        </div>""")

    cards_html = "\n".join(cards)

    return f"""
    <div style="{_OUTER_STYLE}">
      <div style="font-size:16px;font-weight:600;margin-bottom:12px;letter-spacing:.2px;">
        {season_label} &mdash; Predicted Results
      </div>
      {cards_html}
      <div style="color:#5f6368;font-size:11px;margin-top:14px;text-align:center;">
        Typical model error: &plusmn;{shared_uncertainty:.0f} pts on the scoreline &middot;
        bar width = P(home win) &middot; gold = predicted winner
      </div>
    </div>
    """


# ---------------------------------------------------------------------------
# Model-accuracy history view
# ---------------------------------------------------------------------------
# Three card states drive the color scheme:
#   * pending  — fixture not played yet, gray accent
#   * correct  — winner predicted correctly, green accent
#   * wrong    — winner missed, red accent
# The summary strip at the top is the at-a-glance "how is the model doing".


_PENDING_ACCENT = "#5f6368"
_CORRECT_ACCENT = "#00d084"
_WRONG_ACCENT = "#e76f51"


def _accuracy_summary_html(view: pd.DataFrame) -> str:
    """Top strip: total predictions, played, correct, accuracy %."""
    total = len(view)
    played_mask = view["actual_winner"].notna()
    played = int(played_mask.sum())
    pending = total - played
    correct = int((view.loc[played_mask, "winner_correct"] == True).sum())  # noqa: E712
    accuracy = (correct / played * 100.0) if played else 0.0

    pill_style = (
        "background:#171820;border-radius:8px;padding:10px 14px;"
        "display:inline-block;margin-right:10px;min-width:96px;text-align:center;"
    )

    return f"""
    <div style="margin-bottom:16px;">
      <div style="{pill_style}">
        <div style="color:#9aa0a6;font-size:10px;text-transform:uppercase;letter-spacing:1.2px;">Total</div>
        <div style="color:#e7e7ea;font-size:20px;font-weight:700;margin-top:2px;">{total}</div>
      </div>
      <div style="{pill_style}">
        <div style="color:#9aa0a6;font-size:10px;text-transform:uppercase;letter-spacing:1.2px;">Played</div>
        <div style="color:#e7e7ea;font-size:20px;font-weight:700;margin-top:2px;">{played}</div>
      </div>
      <div style="{pill_style}">
        <div style="color:#9aa0a6;font-size:10px;text-transform:uppercase;letter-spacing:1.2px;">Pending</div>
        <div style="color:{_PENDING_ACCENT};font-size:20px;font-weight:700;margin-top:2px;">{pending}</div>
      </div>
      <div style="{pill_style}">
        <div style="color:#9aa0a6;font-size:10px;text-transform:uppercase;letter-spacing:1.2px;">Correct</div>
        <div style="color:{_CORRECT_ACCENT};font-size:20px;font-weight:700;margin-top:2px;">{correct}</div>
      </div>
      <div style="{pill_style}">
        <div style="color:#9aa0a6;font-size:10px;text-transform:uppercase;letter-spacing:1.2px;">Accuracy</div>
        <div style="color:#ffd166;font-size:20px;font-weight:700;margin-top:2px;">{accuracy:.0f}%</div>
      </div>
    </div>
    """


_GOLD = "#ffd166"
_DIM_GRAY = "#5f6368"


def _scoreline_html(home_score: int, away_score: int) -> str:
    """Render a 'H – A' scoreline with the winning side in gold."""
    if home_score > away_score:
        h_color, a_color = _GOLD, _DIM_GRAY
    elif away_score > home_score:
        h_color, a_color = _DIM_GRAY, _GOLD
    else:
        h_color = a_color = "#e7e7ea"
    return (
        f'<span style="color:{h_color};font-weight:700;">{home_score}</span>'
        f' <span style="color:#5f6368;">&ndash;</span> '
        f'<span style="color:{a_color};font-weight:700;">{away_score}</span>'
    )


def _prob_color(prob_pct: int) -> str:
    """Heat-map the home-win probability so confidence is visible at a glance."""
    if prob_pct >= 75:
        return "#00d084"
    if prob_pct >= 60:
        return "#a3d977"
    if prob_pct >= 40:
        return "#cdd0d4"
    if prob_pct >= 25:
        return "#f4a261"
    return "#e76f51"


def _accuracy_row(row: pd.Series) -> str:
    """One <tr> for the aggregated accuracy table."""
    is_played = pd.notna(row["actual_winner"])

    pred_home = int(row["predicted_home_score"])
    pred_away = int(row["predicted_away_score"])
    pred_scoreline = _scoreline_html(pred_home, pred_away)

    if not is_played:
        accent = _PENDING_ACCENT
        # Subtle pending tint — slightly darker than the table base so the row
        # still reads as "future / unresolved" without being noisy.
        row_bg = "#1a1b24"
        status_label = "PENDING"
        status_bg = "#22232a"
        actual_cell = f'<span style="color:{_PENDING_ACCENT};font-style:italic;">awaiting</span>'
        actual_winner_cell = "&mdash;"
    else:
        if bool(row["winner_correct"]):
            accent = _CORRECT_ACCENT
            row_bg = "rgba(0, 208, 132, 0.06)"  # 6% green wash
            status_label = "✓ CORRECT"
            status_bg = "rgba(0, 208, 132, 0.18)"
        else:
            accent = _WRONG_ACCENT
            row_bg = "rgba(231, 111, 81, 0.07)"  # 7% red wash
            status_label = "✗ WRONG"
            status_bg = "rgba(231, 111, 81, 0.18)"
        actual_cell = _scoreline_html(int(row["actual_home_score"]), int(row["actual_away_score"]))
        actual_winner_cell = str(row["actual_winner"])

    prob_pct = round(float(row["home_win_probability"]) * 100)
    prob_color = _prob_color(prob_pct)

    # Highlight team names that won (predicted side bold-gold; actual side bold-gold).
    home_pred_color = _GOLD if row["predicted_winner"] == row["home"] else "#e7e7ea"
    away_pred_color = _GOLD if row["predicted_winner"] == row["away"] else "#e7e7ea"
    home_pred_weight = 700 if row["predicted_winner"] == row["home"] else 400
    away_pred_weight = 700 if row["predicted_winner"] == row["away"] else 400

    return f"""
    <tr style="border-bottom:1px solid #22232a;background:{row_bg};">
      <td style="padding:10px 12px;color:#9aa0a6;font-size:12px;white-space:nowrap;
                 border-left:4px solid {accent};">{row["fixture_date"]}</td>
      <td style="padding:10px 12px;text-align:right;color:{home_pred_color};
                 font-weight:{home_pred_weight};font-size:13px;">
        {row["home"]}
      </td>
      <td style="padding:10px 6px;color:#5f6368;font-size:11px;text-align:center;">vs</td>
      <td style="padding:10px 12px;text-align:left;color:{away_pred_color};
                 font-weight:{away_pred_weight};font-size:13px;">
        {row["away"]}
      </td>
      <td style="padding:10px 12px;text-align:center;font-size:13px;
                 letter-spacing:.4px;white-space:nowrap;">
        {pred_scoreline}
      </td>
      <td style="padding:10px 12px;text-align:center;font-size:13px;white-space:nowrap;
                 letter-spacing:.4px;">
        {actual_cell}
      </td>
      <td style="padding:10px 12px;text-align:center;color:{prob_color};font-size:12px;
                 font-weight:700;font-variant-numeric:tabular-nums;">{prob_pct}%</td>
      <td style="padding:10px 12px;text-align:left;color:{_GOLD};font-size:12px;font-weight:600;">
        {row["predicted_winner"]}
      </td>
      <td style="padding:10px 12px;text-align:left;color:{accent};font-size:12px;font-weight:600;">
        {actual_winner_cell}
      </td>
      <td style="padding:10px 12px;text-align:right;white-space:nowrap;">
        <span style="background:{status_bg};color:{accent};font-size:10px;font-weight:700;
                     letter-spacing:1.2px;padding:4px 10px;border-radius:12px;">
          {status_label}
        </span>
      </td>
    </tr>"""


def render_accuracy_history_html(
    view: pd.DataFrame,
    season_label: str = "GBL 2025/26",
) -> str:
    """Render the model-accuracy history as one self-contained HTML block.

    ``view`` is whatever ``prediction_log.build_accuracy_view()`` returns —
    one row per logged fixture, with actuals merged in where available.
    """
    if view.empty:
        return (
            f"<div style='{_OUTER_STYLE}'>"
            f"<div style='font-size:16px;font-weight:600;margin-bottom:12px;'>"
            f"{season_label} &mdash; Model Accuracy</div>"
            "<p style='color:#888;margin:0;'>No predictions logged yet. "
            "Click <b>Generate Predictions</b> in <code>predictor.ipynb</code> "
            "to start building the history.</p></div>"
        )

    rows = "\n".join(_accuracy_row(row) for _, row in view.iterrows())

    return f"""
    <div style="{_OUTER_STYLE}">
      <div style="font-size:16px;font-weight:600;margin-bottom:12px;letter-spacing:.2px;">
        {season_label} &mdash; Model Accuracy
      </div>
      {_accuracy_summary_html(view)}
      <table style="width:100%;border-collapse:collapse;background:#171820;border-radius:10px;
                    overflow:hidden;">
        <thead>
          <tr style="background:#1c1d26;color:#6b7280;font-size:10px;text-transform:uppercase;
                     letter-spacing:1.3px;">
            <th style="padding:10px 12px;text-align:left;font-weight:500;">Date</th>
            <th style="padding:10px 12px;text-align:right;font-weight:500;">Home</th>
            <th></th>
            <th style="padding:10px 12px;text-align:left;font-weight:500;">Away</th>
            <th style="padding:10px 12px;text-align:center;font-weight:500;">Predicted</th>
            <th style="padding:10px 12px;text-align:center;font-weight:500;">Actual</th>
            <th style="padding:10px 12px;text-align:center;font-weight:500;">P(Home)</th>
            <th style="padding:10px 12px;text-align:left;font-weight:500;">Pick</th>
            <th style="padding:10px 12px;text-align:left;font-weight:500;">Winner</th>
            <th style="padding:10px 12px;text-align:right;font-weight:500;">Outcome</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      <div style="color:#5f6368;font-size:11px;margin-top:14px;text-align:center;line-height:1.7;">
        Logged on each <b>Generate Predictions</b> click; actuals fill in once games are synced.
        <br>
        <span style="color:#ffd166;">●</span> gold = winner &middot;
        <span style="color:#00d084;">●</span> green = correct call &middot;
        <span style="color:#e76f51;">●</span> red = wrong call &middot;
        <span style="color:#5f6368;">●</span> gray = pending &middot;
        P(Home) heat-mapped from red (low) to green (high)
      </div>
    </div>
    """
