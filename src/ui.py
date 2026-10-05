"""Notebook-facing UI helpers.

Keeps the notebook cells short. The whole "fixtures table → button →
predictions" flow lives here so the notebook cell is two lines.

Visual design: a single dark "deck" wraps the fixtures table, the button,
and the prediction slot, so the eye reads top-to-bottom without a jarring
white gap around the bare ipywidgets button. Custom CSS is injected once
to give the button a gradient, hover lift, and proper typography.

Duplication-safe design: we use a single ``widgets.HTML`` widget as the
prediction slot. Setting its ``.value`` property REPLACES the content
in place — there's no clear_output / display / Output-widget dance where
state can accumulate across re-renders or kernel quirks.
"""

from __future__ import annotations

# CSS injected once per notebook session. Targets a custom class name on the
# button widget plus a wrapper class on the action zone, so the styling stays
# scoped and won't leak into other widgets in the same notebook.
_UI_CSS = """
<style>
  .gbl-action-zone {
    background: #0f0f14;
    border-radius: 14px;
    padding: 18px 22px;
    margin-top: -8px;
    border-top: 1px solid #22232a;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  }
  .gbl-action-zone .gbl-action-label {
    color: #9aa0a6;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1.4px;
    margin-bottom: 8px;
    text-align: center;
  }
  /* The widget container that ipywidgets renders the button into. */
  .gbl-action-zone .widget-button {
    margin: 0 !important;
  }
  .gbl-action-zone button.jupyter-button.gbl-predict-btn {
    background: linear-gradient(90deg, #00d084 0%, #ffd166 100%) !important;
    color: #0f0f14 !important;
    border: 0 !important;
    height: 46px !important;
    width: 280px !important;
    font-weight: 700 !important;
    font-size: 14px !important;
    letter-spacing: .6px !important;
    border-radius: 10px !important;
    box-shadow: 0 4px 14px rgba(0, 208, 132, .18);
    transition: transform .12s ease, box-shadow .12s ease, filter .12s ease;
    cursor: pointer;
    text-transform: uppercase;
  }
  .gbl-action-zone button.jupyter-button.gbl-predict-btn:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 8px 22px rgba(0, 208, 132, .28);
    filter: brightness(1.05);
  }
  .gbl-action-zone button.jupyter-button.gbl-predict-btn:active:not(:disabled) {
    transform: translateY(0);
    box-shadow: 0 3px 10px rgba(0, 208, 132, .2);
  }
  .gbl-action-zone button.jupyter-button.gbl-predict-btn:disabled {
    background: #2a2c36 !important;
    color: #6b7280 !important;
    box-shadow: none;
    cursor: not-allowed;
  }
</style>
"""


def show_predictions_ui(bundle) -> None:
    """Show upcoming-fixtures table, a button, and on-click predictions.

    One function = one notebook cell's worth of behavior.
    """
    # Late imports: calling ``import src.ui`` shouldn't drag in ipywidgets
    # unless someone actually invokes this function.
    import ipywidgets as widgets
    from IPython.display import HTML, display

    from src.predict import load_fixtures_from_csv, next_round, predict_fixtures
    from src.prediction_log import append_predictions
    from src.visualize import render_fixtures_table_html, render_predictions_html

    # The CSV holds the whole remaining season — only score the next round.
    fixtures, fixture_dates = next_round(*load_fixtures_from_csv())

    # 1. Inject CSS + render the upcoming-fixtures table. The CSS is harmless
    #    if injected multiple times (idempotent <style> block).
    display(HTML(_UI_CSS))
    display(HTML(render_fixtures_table_html(fixtures)))

    # No fixtures → no point showing the button. Bail out early; the table
    # already renders a friendly "No upcoming fixtures" message.
    if not fixtures:
        return

    # 2. The button — restyled via the gbl-predict-btn class (see _UI_CSS).
    button = widgets.Button(description="Generate Predictions")
    button.add_class("gbl-predict-btn")

    # 3. The prediction slot. Using widgets.HTML (not widgets.Output) is the
    #    key fix: setting .value replaces the entire content atomically. No
    #    clear_output() calls, no "stacking on re-runs" problem.
    prediction_slot = widgets.HTML(
        value="",
        layout=widgets.Layout(width="100%"),
    )

    # 4. Wrap the button + label + slot in a dark "action zone" that visually
    #    extends the fixtures-table container, so there's no white gap.
    action_label = widgets.HTML(
        '<div class="gbl-action-label">Ready &mdash; click to score the slate</div>'
    )
    zone = widgets.VBox(
        [action_label, button, prediction_slot],
        layout=widgets.Layout(
            padding="0",
            margin="0",
            align_items="center",
        ),
    )
    zone.add_class("gbl-action-zone")

    def _on_click(_b):
        _b.disabled = True
        _b.description = "Generating..."
        try:
            preds = predict_fixtures(
                fixtures,
                fixture_dates=fixture_dates,
                bundle=bundle,
            )
            # Persist to the model-accuracy history before rendering. Upsert
            # by fixture key, so re-clicks don't accumulate duplicates.
            append_predictions(preds)
            # Single atomic replacement. No matter how many times the user
            # clicks — once, twice, a hundred times — the slot always shows
            # the ONE most recent set of predictions.
            prediction_slot.value = render_predictions_html(preds)
        finally:
            _b.disabled = False
            _b.description = "Regenerate Predictions"

    button.on_click(_on_click)
    display(zone)
