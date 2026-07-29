"""Interactive accuracy and somatic-performance figures."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def _facet_text(text: str) -> str:
    """Turn Plotly's ``field=value`` facet header into a concise label."""
    if "=" not in text:
        return text
    field, value = text.split("=", 1)
    if field.lower().startswith("coverage"):
        return f"{value}x"
    if field == "biological_class":
        return value.replace("_", " ").title()
    return value


def _use_shared_x_title(
    fig: go.Figure,
    title: str,
    *,
    y_position: float = -0.18,
    bottom_margin: int = 80,
) -> None:
    """Remove repeated facet x titles and add one figure-level title."""
    fig.for_each_annotation(
        lambda annotation: annotation.update(text=_facet_text(annotation.text))
    )
    fig.for_each_xaxis(lambda axis: axis.update(title_text=None))
    fig.add_annotation(
        text=title,
        x=0.5,
        y=y_position,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"size": 14},
    )
    fig.update_layout(margin={"b": bottom_margin})


def _use_shared_y_title(
    fig: go.Figure,
    title: str,
    *,
    x_position: float = -0.07,
    left_margin: int = 90,
) -> None:
    """Remove the repeated per-facet y titles and add one figure-level y title.

    Faceted figures otherwise repeat the y-axis title on every facet row, so with
    ``facet_col_wrap`` the titles stack and overprint each other. Mirror
    :func:`_use_shared_x_title`: clear the per-axis titles and draw one rotated
    title centred on the left edge.
    """
    fig.for_each_yaxis(lambda axis: axis.update(title_text=None))
    fig.add_annotation(
        text=title,
        x=x_position,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        textangle=-90,
        font={"size": 14},
    )
    fig.update_layout(margin={"l": left_margin})


def accuracy_figure(data: pd.DataFrame, title: str, y_label: str) -> go.Figure:
    facet = "biological_class" if "biological_class" in data.columns else None
    fig = px.line(
        data,
        x="coverage",
        y="value",
        color="caller",
        markers=True,
        facet_col=facet,
        facet_col_wrap=3,
        title=title,
        labels={"coverage": "Coverage (x)", "value": y_label, "caller": "Caller"},
    )
    if (
        y_label.endswith("rate")
        or "accuracy" in y_label.lower()
        or "recall" in y_label.lower()
        or "precision" in y_label.lower()
    ):
        fig.update_yaxes(range=[0, 1], tickformat=".0%")
    if facet is not None:
        _use_shared_x_title(fig, "Coverage (x)")
    fig.update_layout(legend_title_text="Caller", hovermode="x unified")
    return fig


def caller_comparison_figure(data: pd.DataFrame, title: str, y_label: str) -> go.Figure:
    x = "biological_class" if "biological_class" in data.columns else "coverage"
    facet = "coverage" if x == "biological_class" else None
    # Each incoming row is a per-slice recall (one per replicate x TE group x
    # cellular fraction). Without aggregating, px.bar sums these for each
    # (caller, x) bar; the summed height then clips against the [0, 1] axis and
    # reads near 100%. Average to one value per bar so the height is the mean
    # recall across the active slice.
    group_cols = [x, "caller"] + ([facet] if facet else [])
    data = data.groupby(group_cols, as_index=False, observed=True)["value"].mean()
    fig = px.bar(
        data,
        x=x,
        y="value",
        color="caller",
        barmode="group",
        facet_col=facet,
        title=title,
        labels={x: x.replace("_", " ").title(), "value": y_label, "caller": "Caller"},
    )
    if y_label != "Mean false-positive calls":
        fig.update_yaxes(range=[0, 1], tickformat=".0%")
    if x == "biological_class":
        # Long categorical tick labels need more separation from the one shared
        # axis title than the short numeric coverage ticks do.
        _use_shared_x_title(
            fig,
            "Biological Class",
            y_position=-0.42,
            bottom_margin=140,
        )
    return fig


def somatic_figure(data: pd.DataFrame) -> go.Figure:
    fig = px.line(
        data,
        x="cellular_fraction",
        y="detection_recall",
        color="caller",
        markers=True,
        facet_col="coverage",
        title="Somatic insertion recall by cellular fraction",
        labels={
            "cellular_fraction": "Cellular fraction",
            "detection_recall": "Detection recall",
            "coverage": "Coverage (x)",
            "caller": "Caller",
        },
        hover_data=["expected_vaf", "detected_events", "truth_events"],
    )
    fig.for_each_annotation(
        lambda annotation: annotation.update(text=_facet_text(annotation.text))
    )
    fig.update_yaxes(range=[0, 1], tickformat=".0%")
    return fig


def te_group_figure(data: pd.DataFrame, title: str, y_label: str) -> go.Figure:
    """Coverage curves faceted by curated TE group."""
    fig = px.line(
        data,
        x="coverage",
        y="value",
        color="caller",
        markers=True,
        facet_col="te_group",
        facet_col_wrap=3,
        title=title,
        labels={
            "coverage": "Coverage (x)",
            "value": y_label,
            "caller": "Caller",
            "te_group": "TE group",
        },
        hover_data=[
            column
            for column in ("te_class", "te_order", "te_superfamily")
            if column in data.columns
        ],
    )
    fig.update_yaxes(range=[0, 1], tickformat=".0%")
    _use_shared_x_title(fig, "Coverage (x)", y_position=-0.12)
    _use_shared_y_title(fig, y_label)
    return fig


def te_group_heatmap(data: pd.DataFrame, title: str) -> go.Figure:
    """Mean metric across selected coverage values for each caller/group."""
    pooled = (
        data.groupby(["caller", "te_group"], as_index=False, observed=True)["value"]
        .mean()
    )
    matrix = pooled.pivot(index="te_group", columns="caller", values="value")
    fig = px.imshow(
        matrix,
        zmin=0,
        zmax=1,
        color_continuous_scale="Viridis",
        text_auto=".0%",
        aspect="auto",
        title=title,
        labels={"x": "Caller", "y": "TE group", "color": "Metric"},
    )
    fig.update_coloraxes(colorbar_tickformat=".0%")
    return fig
