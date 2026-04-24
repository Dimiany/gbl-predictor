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
            "<p style='color:#888;margin:0;'>No upcoming fixtures. "
            "Run <code>python scripts/sync.py --commit</code>.</p></div>"
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
            <div style="font-size:22px;font-weight:700;min-width:96px;text-align:center;letter-spacing:.5px;">
              {p.predicted_home_score} <span style="color:#5f6368;">&ndash;</span> {p.predicted_away_score}
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
