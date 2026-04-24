"""Notebook-facing UI helpers.

Keeps the notebook cells short. The whole "fixtures table → button →
predictions" flow lives here so the notebook cell is two lines.

Duplication-safe design: we use a single ``widgets.HTML`` widget as the
prediction slot. Setting its ``.value`` property REPLACES the content
in place — there's no clear_output / display / Output-widget dance where
state can accumulate across re-renders or kernel quirks.
"""

from __future__ import annotations


def show_predictions_ui(bundle) -> None:
    """Show upcoming-fixtures table, a button, and on-click predictions.

    One function = one notebook cell's worth of behavior.
    """
    # Late imports: calling ``import src.ui`` shouldn't drag in ipywidgets
    # unless someone actually invokes this function.
    import ipywidgets as widgets
    from IPython.display import HTML, display

    from src.predict import load_fixtures_from_csv, predict_fixtures
    from src.visualize import render_fixtures_table_html, render_predictions_html

    fixtures, fixture_dates = load_fixtures_from_csv()

    # 1. Upcoming fixtures as a static HTML block — it doesn't change, so
    #    ``display(HTML(...))`` is fine; nothing to update later.
    display(HTML(render_fixtures_table_html(fixtures)))

    # 2. The button.
    button = widgets.Button(
        description="Generate Predictions",
        button_style="primary",
        layout=widgets.Layout(width="260px", height="40px", margin="12px 0 4px 0"),
    )

    # 3. The prediction slot. Using widgets.HTML (not widgets.Output) is the
    #    key fix: setting .value replaces the entire content atomically. No
    #    clear_output() calls, no "stacking on re-runs" problem.
    prediction_slot = widgets.HTML(value="")

    def _on_click(_b):
        _b.disabled = True
        _b.description = "Generating..."
        try:
            preds = predict_fixtures(
                fixtures,
                fixture_dates=fixture_dates,
                bundle=bundle,
            )
            # Single atomic replacement. No matter how many times the user
            # clicks — once, twice, a hundred times — the slot always shows
            # the ONE most recent set of predictions.
            prediction_slot.value = render_predictions_html(preds)
        finally:
            _b.disabled = False
            _b.description = "Regenerate Predictions"

    button.on_click(_on_click)
    display(button, prediction_slot)
