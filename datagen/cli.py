"""CLI for YumBurger data generation."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from datagen.generator import generate_all, save_parquet

app = typer.Typer(name="yumburger-datagen", help="YumBurger synthetic data generator")
console = Console()


@app.command()
def generate(
    scale: str = typer.Option("small", help="Data scale: small | medium"),
    output_dir: Path = typer.Option(Path("data/raw"), help="Output directory for Parquet files"),
) -> None:
    """Generate synthetic YumBurger data and save as Parquet."""
    console.print(f"[bold green]YumBurger DataGen[/] scale={scale} output={output_dir}")
    dfs = generate_all(scale=scale)
    console.print("\n[bold]Saving Parquet files...[/]")
    save_parquet(dfs, output_dir)
    console.print(f"\n[bold green]Done![/] Files saved to {output_dir}/")


@app.command()
def verify(
    data_dir: Path = typer.Option(Path("data/raw"), help="Directory with Parquet files"),
) -> None:
    """Verify generated Parquet files: row counts and schema."""
    import pandas as pd

    expected_tables = [
        "supplier", "menu_item", "customer", "order", "order_line"
    ]

    table = Table(title="Data Verification", show_header=True)
    table.add_column("Table")
    table.add_column("File Exists", justify="center")
    table.add_column("Row Count", justify="right")
    table.add_column("Columns", justify="right")
    table.add_column("Status", justify="center")

    all_ok = True
    for tbl in expected_tables:
        path = data_dir / f"{tbl}.parquet"
        if not path.exists():
            table.add_row(tbl, "[red]NO[/]", "-", "-", "[red]MISSING[/]")
            all_ok = False
            continue
        df = pd.read_parquet(path)
        status = "[green]OK[/]" if len(df) > 0 else "[red]EMPTY[/]"
        if len(df) == 0:
            all_ok = False
        table.add_row(tbl, "[green]YES[/]", str(len(df)), str(len(df.columns)), status)

    console.print(table)
    if all_ok:
        console.print("\n[bold green]All tables verified OK[/]")
    else:
        console.print("\n[bold red]Verification FAILED[/]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
