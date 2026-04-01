import json
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

console = Console()

def main():
    console.print(Panel(
        "[bold cyan]LifeOS MCP Server — Setup[/bold cyan]",
        expand=False
    ))
    console.print()

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    console.print("  Opening folder picker...")
    console.print()

    vault_path = filedialog.askdirectory(
        title="Select your Obsidian vault folder"
    )
    root.destroy()

    if not vault_path:
        console.print("  [red]✗ No folder selected. Aborting.[/red]")
        return

    vault = Path(vault_path)
    if not vault.exists():
        console.print(f"  [red]✗ Path does not exist: {vault}[/red]")
        return

    config_file = Path(__file__).parent / "lifeos.json"
    config_file.write_text(json.dumps({"vault_root": str(vault)}, indent=2))

    console.print(f"  [green]✓[/green] Vault found: [bold]{vault}[/bold]")
    console.print(f"  [green]✓[/green] Config saved to lifeos.json")
    console.print()
    console.print("  Run [bold]uv run python rebuild_index.py[/bold] to build your first index.")
    console.print()

if __name__ == "__main__":
    main()
