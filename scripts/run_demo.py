"""
run_demo.py — Run a demo sequence of NL queries via the connector.
Requires: make serve (connector running on localhost:8000)
Run via: make demo
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
from rich.console import Console
from rich.table import Table

console = Console()

CONNECTOR_URL = "http://localhost:8000"

DEMO_QUESTIONS = [
    {
        "question": "How many menu items do we have?",
        "persona": "analyst",
        "description": "Simple count query",
    },
    {
        "question": "What are the top 5 most expensive menu items?",
        "persona": "analyst",
        "description": "Top-N with ordering",
    },
    {
        "question": "How many customers are in each loyalty tier?",
        "persona": "admin",
        "description": "Group-by aggregation",
    },
    {
        "question": "What is the total revenue by region?",
        "persona": "admin",
        "description": "Revenue analysis by geography",
    },
    {
        "question": "Which suppliers are in the Northeast region?",
        "persona": "analyst",
        "description": "Filter query",
    },
]


def run_demo():
    console.print("\n[bold blue]YumBurger Connector Demo[/]")
    console.print("=" * 60)

    # Health check
    try:
        resp = httpx.get(f"{CONNECTOR_URL}/health", timeout=5)
        resp.raise_for_status()
        console.print("[green]Connector health: OK[/]\n")
    except Exception as e:
        console.print(f"[red]Connector not reachable at {CONNECTOR_URL}: {e}[/]")
        console.print("Run 'make serve' first.")
        sys.exit(1)

    for i, q in enumerate(DEMO_QUESTIONS, 1):
        console.print(f"[bold]Q{i}: {q['question']}[/] ({q['description']})")
        try:
            resp = httpx.post(
                f"{CONNECTOR_URL}/query",
                json={"question": q["question"], "persona": q["persona"]},
                timeout=60,
            )
            if resp.status_code != 200:
                console.print(f"  [red]Error {resp.status_code}: {resp.text[:200]}[/]")
                continue

            data = resp.json()
            console.print(f"  [dim]SQL: {data['compiled_sql'][:100]}...[/]")
            console.print(f"  Returned {data['row_count']} rows in {data['duration_ms']}ms")

            if data["rows"]:
                tbl = Table(show_header=True, header_style="bold")
                cols = list(data["rows"][0].keys())
                for col in cols:
                    tbl.add_column(col)
                for row in data["rows"][:5]:
                    tbl.add_row(*[str(v) for v in row.values()])
                console.print(tbl)

        except Exception as e:
            console.print(f"  [red]Request failed: {e}[/]")

        console.print()

    console.print("[bold green]Demo complete![/]")


if __name__ == "__main__":
    run_demo()
