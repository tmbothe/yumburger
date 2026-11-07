"""
Bodhi simulator — simulates a Bedrock agent that queries YumBurger
via the FastAPI connector as a user-facing chatbot.

Usage:
    python -m bodhi_sim.agent --question "What are the top burgers?"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx
from rich.console import Console
from rich.markdown import Markdown

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

CONNECTOR_URL = "http://localhost:8000"
console = Console()

def ask(question: str, persona: str = "analyst") -> str:
    """Ask a question and return a natural language answer via the /ask endpoint."""
    console.print(f"\n[bold cyan]YumBot[/]: {question}")
    console.print(f"[dim]Persona: {persona}[/]")

    try:
        resp = httpx.post(
            f"{CONNECTOR_URL}/ask",
            json={"question": question, "persona": persona},
            timeout=120,
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        return "Could not connect to YumBurger connector. Is 'make serve' running?"
    except Exception as e:
        return f"Connector error: {e}"

    data = resp.json()
    console.print(f"[dim]SQL: {data['compiled_sql'][:120]}...[/]")
    console.print(f"[dim]Rows: {data['row_count']} in {data['duration_ms']}ms[/]")
    console.print(f"\n[bold green]Answer:[/] {data['answer']}")
    return data["answer"]


def main() -> None:
    parser = argparse.ArgumentParser(description="YumBot — YumBurger Bodhi Simulator")
    parser.add_argument("--question", "-q", required=True, help="Natural language question")
    parser.add_argument("--persona", "-p", default="analyst", choices=["analyst", "admin"])
    args = parser.parse_args()
    ask(args.question, persona=args.persona)


if __name__ == "__main__":
    main()
