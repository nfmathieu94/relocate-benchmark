"""Interactive compute-resource figures."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def runtime_figure(data: pd.DataFrame) -> go.Figure:
    return px.line(
        data,
        x="coverage",
        y="wall_minutes",
        color="caller",
        markers=True,
        title="Mean wall-clock time",
        labels={"coverage": "Coverage (x)", "wall_minutes": "Wall time (min)", "caller": "Caller"},
    )


def memory_figure(data: pd.DataFrame) -> go.Figure:
    return px.line(
        data,
        x="coverage",
        y="max_rss_gib",
        color="caller",
        markers=True,
        title="Mean peak resident memory",
        labels={"coverage": "Coverage (x)", "max_rss_gib": "Peak RSS (GiB)", "caller": "Caller"},
    )

