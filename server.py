"""
server.py — LifeOS MCP Server

Exposes the Obsidian vault as 9 MCP tools for Claude Code.
Run via: uv run python server.py
"""

import json
import re
import yaml
import fitz  # PyMuPDF

from pathlib import Path
from fastmcp import FastMCP
from rebuild_index import build_index

from config import (
    VAULT_ROOT,
    INDEX_PATH,
    FOLDER_MEMORIA,
    FOLDER_PROJEKTE,
    FOLDER_CLAUDE,
    FOLDER_TEMPLATES,
    FOLDER_ANHAENGE,
    READ_ONLY_FOLDERS,
    WRITE_FOLDERS,
    IGNORED_FOLDERS,
)

# ── Server setup ──────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="lifeos",
    instructions="""
You are connected to the LifeOS vault — Luis's Obsidian second brain.

ALWAYS call get_vault_index at the start of every conversation to load context.

Access rules:
- 1 - Memoria Aeterna/: read-only. Sacred personal notes. NEVER write here.
- 2 - Projekte/: read + write. Always add 'ai-collab' tag when writing.
- 3 - Claude/: read + write. Your own space, write freely.
- 5 - Anhänge/: read-only. PDFs and attachments.
- 4 - Templates/: ignored entirely.

When referencing notes, output clickable obsidian:// URI links.
Format: obsidian://open?vault=LifeOS&file=<url-encoded-path>

When creating notes, use [[wikilinks]] to connect to relevant Memoria Aeterna notes.
Use get_tags() to reuse existing tags instead of inventing new ones.

Frontmatter convention:
  date: DD-MM-YYYY
  tags: [array]
  aliases: [array]
  status: aktiv | abgeschlossen | pausiert  (optional)

The vault is multilingual — mostly German, some English. Match the language of the note.
""",
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def find_note(filename: str) -> Path | None:
    """Find a note via index first, fall back to recursive search."""
    name = Path(filename).name

    if INDEX_PATH.exists():
        try:
            index = json.loads(INDEX_PATH.read_text())
            for note in index.get("notes", []):
                if note["filename"] == name or note["path"] == filename:
                    return VAULT_ROOT / note["path"]
        except (json.JSONDecodeError, KeyError):
            pass

    direct = VAULT_ROOT / filename
    if direct.exists():
        return direct

    for md_file in VAULT_ROOT.rglob("*.md"):
        if md_file.name == name:
            return md_file

    return None


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from note body."""
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


def is_readable(path) -> bool:
    """True if Claude is allowed to read this path."""
    parts = path.relative_to(VAULT_ROOT).parts
    return not any(part in IGNORED_FOLDERS for part in parts)


def is_writable(path) -> bool:
    """True if Claude is allowed to write to this path."""
    parts = path.relative_to(VAULT_ROOT).parts
    return any(part in WRITE_FOLDERS for part in parts)


def enforce_ai_collab(frontmatter: dict) -> dict:
    """Ensure ai-collab tag is present in frontmatter."""
    tags = frontmatter.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    if "ai-collab" not in tags:
        tags.append("ai-collab")
    frontmatter["tags"] = tags
    return frontmatter


def render_frontmatter(fm: dict) -> str:
    """Serialize frontmatter dict back to YAML block."""
    return "---\n" + yaml.dump(fm, allow_unicode=True, sort_keys=False) + "---\n"


# ── Read tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def get_vault_index() -> str:
    """
    Load the full vault index with per-note summaries, metadata, wikilinks,
    word counts, and a changelog of recent changes.
    Call this at the start of every conversation.
    """
    if not INDEX_PATH.exists():
        return (
            "vault_index.json not found. "
            "Run `uv run python rebuild_index.py` to build the index first."
        )
    return INDEX_PATH.read_text(encoding="utf-8")


@mcp.tool()
def read_note(filename: str) -> str:
    """
    Read the full content of a note by filename or relative path.
    Searches all vault folders automatically.

    Args:
        filename: Note filename (e.g. 'My Note.md') or relative path
    """
    path = find_note(filename)
    if path is None:
        return f"Note not found: {filename}"
    if not is_readable(path):
        return f"Access denied: {filename} is in an ignored folder."
    return path.read_text(encoding="utf-8", errors="ignore")


@mcp.tool()
def search_notes(
    query: str = "",
    tags: list[str] | None = None,
    folder: str = "",
    status: str = "",
) -> str:
    """
    Search notes by text query, tags, folder, or status.
    At least one filter required.
    Returns matching notes with filename, folder, tags, and a context snippet.

    Args:
        query:  Full-text search string
        tags:   List of tags to filter by (all must match)
        folder: Folder name to restrict search to
        status: Note status to filter by (e.g. 'aktiv')
    """
    if not any([query, tags, folder, status]):
        return "Provide at least one filter: query, tags, folder, or status."

    results = []

    for md_file in VAULT_ROOT.rglob("*.md"):
        if not is_readable(md_file):
            continue

        rel_parts = md_file.relative_to(VAULT_ROOT).parts

        if folder and not any(folder.lower() in part.lower() for part in rel_parts):
            continue

        text = md_file.read_text(encoding="utf-8", errors="ignore")
        fm, body = parse_frontmatter(text)

        if tags:
            note_tags = fm.get("tags") or []
            if isinstance(note_tags, str):
                note_tags = [note_tags]
            if not all(t in note_tags for t in tags):
                continue

        if status and fm.get("status", "").lower() != status.lower():
            continue

        snippet = ""
        if query:
            idx = body.lower().find(query.lower())
            if idx == -1:
                continue
            start = max(0, idx - 50)
            end = min(len(body), idx + 100)
            snippet = "..." + body[start:end].replace("\n", " ") + "..."

        results.append({
            "filename": md_file.name,
            "folder": str(md_file.parent.relative_to(VAULT_ROOT)),
            "path": str(md_file.relative_to(VAULT_ROOT)),
            "tags": fm.get("tags", []),
            "status": fm.get("status", ""),
            "snippet": snippet,
        })

    if not results:
        return "No notes found matching the given filters."

    return json.dumps(results, indent=2, ensure_ascii=False)


@mcp.tool()
def get_wikilinks(filename: str = "") -> str:
    """
    Without filename: returns the full vault link graph as an adjacency list.
    With filename: returns outgoing links and backlinks for that specific note.

    Args:
        filename: Optional note filename to get links for
    """
    pattern = re.compile(r"\[\[([^\]|#]+)(?:[|\#][^\]]*)?\]\]")

    graph: dict[str, list[str]] = {}
    for md_file in VAULT_ROOT.rglob("*.md"):
        if not is_readable(md_file):
            continue
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        graph[md_file.stem] = pattern.findall(text)

    if not filename:
        return json.dumps(graph, indent=2, ensure_ascii=False)

    stem = Path(filename).stem
    outgoing = graph.get(stem, [])
    backlinks = [note for note, links in graph.items() if stem in links]

    return json.dumps({
        "note": stem,
        "outgoing": outgoing,
        "backlinks": backlinks,
    }, indent=2, ensure_ascii=False)


@mcp.tool()
def read_pdf(filename: str, pages: str = "") -> str:
    """
    Extract text from a PDF in the Anhänge folder.

    Args:
        filename: PDF filename (e.g. 'lecture01.pdf')
        pages:    Optional page range, e.g. '1-5' or '3'
    """
    anhaenge = VAULT_ROOT / FOLDER_ANHAENGE
    candidates = list(anhaenge.rglob(filename))
    if not candidates:
        return f"PDF not found in {FOLDER_ANHAENGE}/: {filename}"

    pdf_path = candidates[0]

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        return f"Failed to open PDF: {e}"

    total = len(doc)
    if pages:
        try:
            if "-" in pages:
                start, end = pages.split("-")
                page_range = range(int(start) - 1, min(int(end), total))
            else:
                page_range = range(int(pages) - 1, int(pages))
        except ValueError:
            return f"Invalid page range: {pages}. Use '1-5' or '3'."
    else:
        page_range = range(total)

    text_parts = []
    for i in page_range:
        page_text = doc[i].get_text()
        text_parts.append(f"--- Page {i + 1} ---\n{page_text}")

    doc.close()
    return "\n\n".join(text_parts)


@mcp.tool()
def get_vault_stats() -> str:
    """
    Returns vault statistics: note counts per folder, tag frequency,
    5 most recently modified notes, open checklist items, active projects,
    and unresolved wikilinks.
    """
    from collections import Counter

    note_counts: Counter = Counter()
    tag_counts: Counter = Counter()
    recent: list[tuple[float, str]] = []
    open_checklists: list[dict] = []
    active_projects: list[str] = []
    all_stems: set[str] = set()
    all_links: list[tuple[str, str]] = []

    for md_file in VAULT_ROOT.rglob("*.md"):
        if not is_readable(md_file):
            continue

        folder = str(md_file.parent.relative_to(VAULT_ROOT))
        note_counts[folder] += 1
        all_stems.add(md_file.stem)

        text = md_file.read_text(encoding="utf-8", errors="ignore")
        fm, body = parse_frontmatter(text)

        tags = fm.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        for tag in tags:
            tag_counts[tag] += 1

        mtime = md_file.stat().st_mtime
        recent.append((mtime, str(md_file.relative_to(VAULT_ROOT))))

        for line in body.splitlines():
            if line.strip().startswith("- [ ]"):
                open_checklists.append({
                    "note": md_file.name,
                    "item": line.strip()[6:],
                })

        if fm.get("status", "").lower() == "aktiv":
            active_projects.append(str(md_file.relative_to(VAULT_ROOT)))

        links = re.findall(r"\[\[([^\]|#]+)(?:[|\#][^\]]*)?\]\]", text)
        for link in links:
            all_links.append((md_file.name, link.strip()))

    unresolved = [
        {"from": src, "link": link}
        for src, link in all_links
        if link not in all_stems
    ]

    recent_sorted = [path for _, path in sorted(recent, reverse=True)[:5]]

    stats = {
        "note_counts_per_folder": dict(note_counts.most_common()),
        "tag_frequency": dict(tag_counts.most_common(20)),
        "recently_modified": recent_sorted,
        "open_checklist_items": open_checklists[:20],
        "active_projects": active_projects,
        "unresolved_wikilinks": unresolved[:20],
    }

    return json.dumps(stats, indent=2, ensure_ascii=False)


@mcp.tool()
def get_tags() -> str:
    """
    Returns all tags used in the vault with frequency counts.
    Use this before creating notes to reuse existing tags consistently.
    """
    from collections import Counter
    tag_counts: Counter = Counter()

    for md_file in VAULT_ROOT.rglob("*.md"):
        if not is_readable(md_file):
            continue
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        fm, _ = parse_frontmatter(text)
        tags = fm.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        for tag in tags:
            tag_counts[tag] += 1

    return json.dumps(dict(tag_counts.most_common()), indent=2, ensure_ascii=False)


# ── Write tools ───────────────────────────────────────────────────────────────

@mcp.tool()
def create_note(filename: str, content: str, folder: str = "") -> str:
    """
    Create a new note in the vault. Defaults to the Claude folder (AI's own space).
    If folder is Projekte/, enforces the ai-collab tag automatically.

    Args:
        filename: Note filename including .md extension
        content:  Full note content (include frontmatter if desired)
        folder:   Target folder name (defaults to '3 - Claude')
    """
    target_folder = folder if folder else FOLDER_CLAUDE
    target_path = VAULT_ROOT / target_folder / filename

    try:
        rel_parts = target_path.relative_to(VAULT_ROOT).parts
    except ValueError:
        return "Access denied: path escapes vault root."

    if any(part in READ_ONLY_FOLDERS + IGNORED_FOLDERS for part in rel_parts):
        return f"Access denied: cannot write to {target_folder}. Use '{FOLDER_PROJEKTE}' or '{FOLDER_CLAUDE}'."

    if target_path.exists():
        return f"Note already exists: {target_path.relative_to(VAULT_ROOT)}. Use edit_note to update it."

    fm, body = parse_frontmatter(content)
    if FOLDER_PROJEKTE in str(target_path):
        fm = enforce_ai_collab(fm)
        content = render_frontmatter(fm) + "\n" + body

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")

    return f"Created: {target_path.relative_to(VAULT_ROOT)}"


@mcp.tool()
def edit_note(filename: str, content: str) -> str:
    """
    Replace the full content of an existing note in Projekte/ or Claude/.
    Automatically adds the ai-collab tag if missing in Projekte/ notes.
    Cannot edit notes in Memoria Aeterna/ (read-only).

    Args:
        filename: Note filename or relative path
        content:  New full content for the note
    """
    path = find_note(filename)

    if path is None:
        return f"Note not found: {filename}"

    if not is_writable(path):
        return f"Access denied: '{filename}' is read-only. Claude can only edit notes in '{FOLDER_PROJEKTE}' or '{FOLDER_CLAUDE}'."

    fm, body = parse_frontmatter(content)
    if FOLDER_PROJEKTE in str(path):
        fm = enforce_ai_collab(fm)
        content = render_frontmatter(fm) + "\n" + body

    path.write_text(content, encoding="utf-8")
    return f"Updated: {path.relative_to(VAULT_ROOT)}"


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    build_index()
    mcp.run(transport="stdio")
