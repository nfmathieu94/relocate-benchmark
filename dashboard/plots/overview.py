"""Cross-dataset comparison figures for the RelocaTE3-vs-RelocaTE2 page.

Axis naming follows the rest of the dashboard so the two never disagree:
``Coverage (x)``, ``Caller``, ``Detection recall``, and -- matching the
sidebar filter and the Information glossary -- ``TE divergence (%)``.

Faceted figures route their x title through :func:`_use_shared_x_title` for
the same reason the accuracy page does: Plotly otherwise repeats the axis
title once per facet, and the copies stack and overprint each other.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .accuracy import _facet_text, _use_shared_x_title

#: The wording used by the sidebar filter and the Information glossary.
DIVERGENCE_LABEL = "TE divergence (%)"


def dataset_comparison_figure(
    summary: pd.DataFrame, metric: str, y_label: str
) -> go.Figure:
    """One grouped bar per dataset, coloured by caller.

    Unfaceted, so the axis titles stay on the axes; there is nothing to
    de-duplicate here.
    """
    fig = px.bar(
        summary,
        x="dataset_label",
        y=metric,
        color="caller",
        barmode="group",
        text_auto=".3f",
        labels={
            "dataset_label": "Dataset",
            metric: y_label,
            "caller": "Caller",
        },
    )
    fig.update_yaxes(range=[0, 1])
    fig.update_layout(legend_title_text="Caller")
    return fig


def divergence_figure(data: pd.DataFrame) -> go.Figure:
    """Detection recall against percent divergence, faceted by coverage.

    Mirrors :func:`somatic_figure`: facet headers are rewritten from
    ``coverage=5`` to ``5x``, and the repeated per-facet x titles collapse to
    a single figure-level one.
    """
    fig = px.line(
        data,
        x="divergence_percent",
        y="recall",
        color="caller",
        markers=True,
        facet_col="coverage",
        labels={
            "divergence_percent": DIVERGENCE_LABEL,
            "recall": "Detection recall",
            "coverage": "Coverage (x)",
            "caller": "Caller",
        },
    )
    fig.update_yaxes(range=[0, 1], tickformat=".0%")
    # Only the divergence levels actually simulated, so the axis does not
    # invent intermediate ticks between them.
    fig.update_xaxes(
        tickmode="array",
        tickvals=sorted(data["divergence_percent"].dropna().unique().tolist()),
    )
    _use_shared_x_title(fig, DIVERGENCE_LABEL)
    fig.update_layout(legend_title_text="Caller", hovermode="x unified")
    return fig
