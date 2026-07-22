"""
Генератор графиков статистики (матплотлиб).
Без seaborn — только matplotlib.
"""

from __future__ import annotations

import io
import logging
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

logger = logging.getLogger(__name__)

BG_COLOR = "#1a1a2e"
TEXT_COLOR = "#e0e0e0"
GRID_COLOR = "#2a2a4e"
UP_COLOR = "#00e676"
DOWN_COLOR = "#ff1744"
NEUTRAL_COLOR = "#ffd600"
ACCENT_COLOR = "#7c4dff"


def _setup_style() -> None:
    plt.style.use("dark_background")


def win_loss_chart(wins: int, losses: int, pending: int) -> io.BytesIO:
    _setup_style()
    fig, ax = plt.subplots(figsize=(6, 6), facecolor=BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    labels = []
    sizes = []
    colors = []
    explode = []

    if wins > 0:
        labels.append(f"Profit ({wins})")
        sizes.append(wins)
        colors.append(UP_COLOR)
        explode.append(0.05)
    if losses > 0:
        labels.append(f"Loss ({losses})")
        sizes.append(losses)
        colors.append(DOWN_COLOR)
        explode.append(0.05)
    if pending > 0:
        labels.append(f"Open ({pending})")
        sizes.append(pending)
        colors.append(NEUTRAL_COLOR)
        explode.append(0.02)

    if not sizes:
        ax.text(0.5, 0.5, "No data", ha="center", va="center",
                fontsize=16, color=TEXT_COLOR, transform=ax.transAxes)
        ax.set_xlim(-1, 1)
        ax.set_ylim(-1, 1)
    else:
        wedges, texts, autotexts = ax.pie(
            sizes, labels=labels, colors=colors,
            explode=tuple(explode), autopct="%1.1f%%",
            startangle=90,
            textprops={"color": TEXT_COLOR, "fontsize": 11, "fontweight": "bold"},
            pctdistance=0.75,
        )
        for autotext in autotexts:
            autotext.set_color("white")
            autotext.set_fontsize(10)

        centre_circle = plt.Circle((0, 0), 0.50, fc=BG_COLOR, edgecolor=ACCENT_COLOR, linewidth=2)
        fig.gca().add_artist(centre_circle)

        total = wins + losses + pending
        ax.text(0, 0, f"{total}\ntrades", ha="center", va="center",
                fontsize=14, color=TEXT_COLOR, fontweight="bold")

    ax.set_title("Trade Statistics", fontsize=14, color=TEXT_COLOR,
                 fontweight="bold", pad=20)

    buf = _fig_to_buffer(fig)
    plt.close(fig)
    return buf


def win_rate_gauge(win_rate: float) -> io.BytesIO:
    _setup_style()
    fig, ax = plt.subplots(figsize=(6, 4), facecolor=BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    angle = win_rate / 100 * 180
    angle_rad = np.deg2rad(angle)
    theta = np.linspace(0, np.pi, 100)
    r = 0.8

    for i in range(len(theta) - 1):
        t = theta[i]
        t_next = theta[i + 1]
        color = plt.cm.RdYlGn(1 - t / np.pi)
        ax.fill_between(
            [r * np.cos(t), r * np.cos(t_next)],
            0, [r * np.sin(t), r * np.sin(t_next)],
            color=color, alpha=0.8, linewidth=0,
        )

    ax.arrow(0, 0, r * 0.75 * np.cos(angle_rad), r * 0.75 * np.sin(angle_rad),
             head_width=0.08, head_length=0.1, fc="white", ec="white", linewidth=2, alpha=0.9)

    circle = plt.Circle((0, 0), 0.12, fc=BG_COLOR, edgecolor=ACCENT_COLOR, linewidth=2)
    ax.add_artist(circle)

    ax.text(0, -0.15, f"{win_rate:.1f}%", ha="center", va="center",
            fontsize=18, color="white", fontweight="bold")
    ax.text(-0.9, -0.2, "0%", fontsize=9, color=TEXT_COLOR, ha="center")
    ax.text(0.9, -0.2, "100%", fontsize=9, color=TEXT_COLOR, ha="center")
    ax.text(0, -0.35, "Win Rate", fontsize=12, color=TEXT_COLOR,
            ha="center", fontweight="bold")

    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-0.4, 1.1)
    ax.axis("off")

    buf = _fig_to_buffer(fig)
    plt.close(fig)
    return buf


def _fig_to_buffer(fig: plt.Figure, dpi: int = 120) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor(), edgecolor="none")
    buf.seek(0)
    return buf
