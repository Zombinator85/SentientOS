"""Flet GUI for live reasoning visualization."""
from __future__ import annotations

import asyncio
import json
from typing import Any

import flet as ft
import networkx as nx
from flet.canvas import Canvas, Circle, Line

from parliament_bus import ParliamentBus, bus
from sentientos.parliament_bus import Turn
from reason_graph import build_graph


class ReasoningPanel(ft.UserControl):  # type: ignore[misc]
    """Panel displaying turns from the ``ParliamentBus``."""

    def __init__(self, bus: ParliamentBus) -> None:
        super().__init__()
        self.bus = bus
        self.tone_heading = ft.Text("Current Tone")
        self.timeline = ft.ListView(spacing=5, expand=True, auto_scroll=True)
        self.detail = ft.TextField(multiline=True, read_only=True, expand=True)
        self.canvas = Canvas(visible=False, expand=True)
        self.graph_toggle = ft.Switch(label="Graph", on_change=self._on_graph_toggle)
        self.export_btn = ft.ElevatedButton("Export", on_click=self._on_export)
        self.turns: list[dict[str, Any]] = []

    def build(self) -> ft.Control:
        right = ft.Column([
            self.detail,
            self.graph_toggle,
            self.canvas,
            self.export_btn,
        ], expand=True)
        return ft.Row([
            ft.Container(ft.Column([self.tone_heading, self.timeline]), width=250),
            right,
        ], expand=True)

    def _show_detail(self, turn: dict[str, Any]) -> None:
        self.detail.value = json.dumps(turn, indent=2)
        self.detail.update()
        if self.graph_toggle.value:
            self._draw_graph(turn)

    def _on_graph_toggle(self, e: ft.ControlEvent) -> None:
        self.canvas.visible = e.control.value
        self.canvas.update()
        if e.control.value and self.turns:
            self._draw_graph(self.turns[-1])

    def _draw_graph(self, _turn: dict[str, Any]) -> None:
        self.canvas.controls.clear()
        # Convert stored turns to ``Turn`` objects for graph building
        conv = [
            Turn(
                speaker=t.get("agent", ""),
                text=str(t.get("text") or t.get("message") or ""),
                emotion=t.get("emotion"),
            )
            for t in self.turns
        ]
        g = build_graph(conv)
        if g.number_of_nodes() == 0:
            self.canvas.update()
            return
        pos = nx.spring_layout(g, seed=42)
        w, h = 400, 400
        Tooltip = getattr(ft, "Tooltip", None)
        for u, v, data in g.edges(data=True):
            x1, y1 = pos[u]
            x2, y2 = pos[v]
            line = Line(w * x1, h * y1, w * x2, h * y2)
            tip = f"{data.get('tokens', 0)} tok / {data.get('latency_ms', 0)} ms"
            self.canvas.controls.append(Tooltip(tip, line) if Tooltip else line)
        for n in g.nodes():
            x, y = pos[n]
            circ = Circle(w * x, h * y, 8)
            self.canvas.controls.append(Tooltip(str(n), circ) if Tooltip else circ)
        self.canvas.update()

    async def _on_export(self, e: ft.ControlEvent) -> None:
        path = self.bus.export()
        await self.page.dialog(ft.AlertDialog(title=ft.Text("Exported"), content=ft.Text(str(path)))).open_async()

    async def subscribe(self) -> None:
        async for turn in self.bus.subscribe():
            self.turns.append(turn)
            tile = ft.ListTile(
                title=ft.Text(f"{turn.get('turn_id')}: {turn.get('agent')}"),
                subtitle=ft.Text(str(turn.get('timestamp'))),
                trailing=ft.Text(str(turn.get('emotion') or "")),
                on_click=lambda e, t=turn: self._show_detail(t),
            )
            self.timeline.controls.append(tile)
            self.timeline.update()


async def main(page: ft.Page) -> None:
    panel = ReasoningPanel(bus)
    page.add(panel)
    asyncio.create_task(panel.subscribe())


if __name__ == "__main__":
    ft.app(target=main)
