"""Emotion Visualizer panel for Flet or PySide6 GUI."""
from __future__ import annotations

import asyncio
import csv
from pathlib import Path
from typing import List

from sentientos.parliament_bus import ParliamentBus, Turn


bus = ParliamentBus()


class EmotionVisualizer:
    """Realtime emotion timeline display compatible with Flet or PySide6."""

    def __init__(self, bus: ParliamentBus) -> None:
        self.bus = bus
        self.history: List[Turn] = []

        self._mode: str = "none"
        self.control: object | None = None

        # Flet setup
        try:
            import flet as ft

            self._ft = ft
            self._mode = "flet"
            self._chart = ft.BarChart(bar_groups=[], expand=True)
            self._list = ft.ListView(auto_scroll=True, expand=True, spacing=5)
            self._export = ft.ElevatedButton("Export CSV", on_click=self._on_export)
            self.control = ft.Column([
                self._chart,
                self._list,
                self._export,
            ], expand=True)
        except Exception:
            # Lazy import PySide6 only if available
            try:
                from PySide6.QtWidgets import (
                    QWidget,
                    QVBoxLayout,
                    QListWidget,
                    QPushButton,
                )
                from PySide6.QtCharts import QChart, QChartView, QBarSeries, QBarSet
                self._mode = "pyside"
                self._widget = QWidget()
                layout = QVBoxLayout(self._widget)
                self._chartset = QBarSet("Emotions")
                self._series = QBarSeries()
                self._series.append(self._chartset)
                chart = QChart()
                chart.addSeries(self._series)
                self._chart_view = QChartView(chart)
                layout.addWidget(self._chart_view)
                self._list = QListWidget()
                layout.addWidget(self._list)
                self._button = QPushButton("Export CSV")
                self._button.clicked.connect(lambda: asyncio.create_task(self._export_csv()))
                layout.addWidget(self._button)
                self.control = self._widget
            except Exception:
                self._mode = "none"
                self.control = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build(self) -> object | None:
        """Return the root GUI control for this panel."""

        return self.control

    async def subscribe(self) -> None:
        """Listen for bus turns and update the display."""

        async for turn in self.bus.subscribe():
            self.history.append(turn)
            emotion = turn.emotion or ""
            if self._mode == "flet":
                rod = self._ft.BarChartRod(
                    from_y=0,
                    to_y=1,
                    color=self._color_for(emotion),
                    tooltip=f"{turn.speaker}: {emotion}",
                )
                group = self._ft.BarChartGroup(x=len(self.history), bar_rods=[rod])
                self._chart.bar_groups.append(group)
                self._chart.update()
                item = self._ft.ListTile(
                    title=self._ft.Text(emotion or "?"),
                    subtitle=self._ft.Text(turn.speaker),
                )
                self._list.controls.append(item)
                self._list.update()
            elif self._mode == "pyside":
                self._chartset << 1
                self._list.addItem(f"{turn.speaker}: {emotion}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _color_for(self, emotion: str) -> str:
        """Return a chart color for ``emotion``."""

        if self._mode != "flet":
            return "gray"
        ft = self._ft
        table = {
            "joy": ft.colors.YELLOW,
            "anger": ft.colors.RED,
            "sadness": ft.colors.BLUE,
            "fear": ft.colors.PURPLE,
            "surprise": ft.colors.ORANGE,
            "disgust": ft.colors.GREEN,
        }
        return table.get(emotion.lower(), ft.colors.GREY)

    async def _export_csv(self) -> Path:
        """Write emotion history to ``logs/emotions`` and return path."""

        path = Path("logs/emotions") / f"{self.bus.cycle_id}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["index", "speaker", "emotion"])
            for i, t in enumerate(self.history, 1):
                writer.writerow([i, t.speaker, t.emotion or ""])
        return path

    async def _on_export(self, e: object) -> None:
        if self._mode != "flet":  # only Flet uses event handler
            return
        path = await self._export_csv()
        await self._ft.dialogs.AlertDialog(
            title=self._ft.Text("Exported"),
            content=self._ft.Text(str(path)),
        ).open_async()


async def main(page) -> None:
    """Run the emotion visualizer as a standalone Flet app."""

    panel = EmotionVisualizer(bus)
    if panel.control is not None:
        page.add(panel.control)
        if panel._mode == "flet":
            asyncio.create_task(panel.subscribe())


if __name__ == "__main__":
    try:
        import flet as ft

        ft.app(target=main)
    except Exception:
        print("Flet is required to run this demo")
