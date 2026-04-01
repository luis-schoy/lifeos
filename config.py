from pathlib import Path
import json

# ── Vault root (written by setup.py, stored in lifeos.json) ──────────────────
_config_file = Path(__file__).parent / "lifeos.json"

if not _config_file.exists():
    raise FileNotFoundError(
        "lifeos.json not found. Run `uv run python setup.py` first."
    )

VAULT_ROOT = Path(json.loads(_config_file.read_text())["vault_root"])

# ── Folder names (access zones) ───────────────────────────────────────────────
FOLDER_MEMORIA   = "1 - Memoria Aeterna"  # human-only: Claude reads, never writes
FOLDER_PROJEKTE  = "2 - Projekte"         # shared: Claude reads + writes (ai-collab tag)
FOLDER_CLAUDE    = "3 - Claude"           # AI-only: Claude writes freely
FOLDER_TEMPLATES = "4 - Templates"        # ignored entirely
FOLDER_ANHAENGE  = "5 - Anhänge"          # attachments: read-only (PDFs)

# ── Access rules ──────────────────────────────────────────────────────────────
READ_ONLY_FOLDERS = [FOLDER_MEMORIA, FOLDER_ANHAENGE]
WRITE_FOLDERS     = [FOLDER_PROJEKTE, FOLDER_CLAUDE]
IGNORED_FOLDERS   = [FOLDER_TEMPLATES, ".lifeos"]

# ── Index ─────────────────────────────────────────────────────────────────────
INDEX_PATH = VAULT_ROOT / ".lifeos" / "vault_index.json"
