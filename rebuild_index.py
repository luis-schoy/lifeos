"""
rebuild_index.py — LifeOS vault index builder

Scans the vault, extracts metadata + summaries from every note,
and writes vault_index.json. Run manually or called automatically by server.py.
"""

import json
import re
import yaml
from datetime import datetime
from pathlib import Path

from config import (
    VAULT_ROOT,
    INDEX_PATH,
    IGNORED_FOLDERS,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from note body. Returns (frontmatter_dict, body)."""
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            raw_yaml = text[3:end].strip()
            body = text[end + 3:].strip()
            try:
                return yaml.safe_load(raw_yaml) or {}, body
            except yaml.YAMLError:
                pass
    return {}, text


def extract_summary(body: str, max_chars: int = 300) -> str:
    """
    Extractive summary: first 2-3 meaningful sentences from the note body.
    Skips headings, empty lines, code blocks, and table rows.
    Falls back to heading titles for bullet-point-only notes.
    """
    sentences = []
    total = 0
    in_code_block = False

    for line in body.splitlines():
        line = line.strip()

        if line.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if not line or line.startswith("#") or line.startswith("|") or line.startswith("!"):
            continue

        clean = re.sub(r"\[\[([^\]]+)\]\]", r"\1", line)
        clean = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", clean)
        clean = re.sub(r"[*_`]", "", clean)

        if len(clean) < 10:
            continue

        sentences.append(clean)
        total += len(clean)
        if total >= max_chars or len(sentences) >= 3:
            break

    if sentences:
        return " ".join(sentences)[:max_chars]

    # Fallback for bullet-point / heading-only notes
    headings = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("#"):
            clean = re.sub(r"^#+\s*", "", line)
            if len(clean) >= 3:
                headings.append(clean)
        if len(headings) >= 4:
            break

    return " · ".join(headings)[:max_chars] if headings else ""


def extract_wikilinks(text: str) -> list[str]:
    """Return all [[wikilink]] targets from a note."""
    return re.findall(r"\[\[([^\]|#]+)(?:[|\#][^\]]*)?\]\]", text)


def get_relative_folder(path: Path) -> str:
    """Return folder path relative to vault root."""
    return str(path.parent.relative_to(VAULT_ROOT))


def is_ignored(path: Path) -> bool:
    """True if this path lives inside an ignored folder."""
    parts = path.relative_to(VAULT_ROOT).parts
    return any(part in IGNORED_FOLDERS for part in parts)


# ── Index builder ─────────────────────────────────────────────────────────────

def build_index() -> dict:
    # Load previous index for changelog comparison
    previous_paths: set[str] = set()
    previous_modified: dict[str, str] = {}

    if INDEX_PATH.exists():
        try:
            old = json.loads(INDEX_PATH.read_text())
            for note in old.get("notes", []):
                previous_paths.add(note["path"])
                previous_modified[note["path"]] = note.get("modified", "")
        except (json.JSONDecodeError, KeyError):
            pass

    notes = []
    current_paths: set[str] = set()

    for md_file in sorted(VAULT_ROOT.rglob("*.md")):
        if is_ignored(md_file):
            continue

        rel_path = str(md_file.relative_to(VAULT_ROOT))
        current_paths.add(rel_path)

        text = md_file.read_text(encoding="utf-8", errors="ignore")
        frontmatter, body = parse_frontmatter(text)
        modified = datetime.fromtimestamp(md_file.stat().st_mtime).isoformat(timespec="seconds")

        notes.append({
            "filename": md_file.name,
            "folder": get_relative_folder(md_file),
            "path": rel_path,
            "frontmatter": frontmatter,
            "summary": extract_summary(body),
            "wikilinks": extract_wikilinks(text),
            "word_count": len(body.split()),
            "modified": modified,
        })

    new_notes      = sorted(current_paths - previous_paths)
    deleted_notes  = sorted(previous_paths - current_paths)
    modified_notes = sorted(
        p for p in current_paths & previous_paths
        if previous_modified.get(p, "") != next(
            (n["modified"] for n in notes if n["path"] == p), ""
        )
    )

    index = {
        "rebuilt_at": datetime.now().isoformat(timespec="seconds"),
        "note_count": len(notes),
        "changelog": {
            "new": new_notes,
            "modified": modified_notes,
            "deleted": deleted_notes,
        },
        "notes": notes,
    }

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False))

    return index


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    console.print(Panel("[bold cyan]LifeOS — Rebuilding vault index[/bold cyan]", expand=False))
    console.print()

    index = build_index()

    console.print(f"  [green]✓[/green] Indexed [bold]{index['note_count']}[/bold] notes")

    cl = index["changelog"]
    if cl["new"]:
        console.print(f"  [green]+ {len(cl['new'])} new[/green]")
    if cl["modified"]:
        console.print(f"  [yellow]~ {len(cl['modified'])} modified[/yellow]")
    if cl["deleted"]:
        console.print(f"  [red]- {len(cl['deleted'])} deleted[/red]")

    console.print(f"\n  Index saved to [bold]{INDEX_PATH}[/bold]")
    console.print()
