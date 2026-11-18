#!/usr/bin/env python3
"""Keep a local, Obsidian-style vault of your Manifest ideas, documents and notes.

Your agent runs this; it needs only Python 3.9+ and never talks to the network.

    manifest_vault.py sync  [--vault DIR] [EXPORT.json | -]   write a vault_export result
    manifest_vault.py note  [--vault DIR] --title T [--idea "Idea title" ...] [--tag t ...] [TEXT | -]
    manifest_vault.py since [--vault DIR]                      print the last sync time
    manifest_vault.py where [--vault DIR]                      print the vault folder

The vault is ``$MANIFEST_VAULT`` or ``~/Manifest Vault`` unless ``--vault`` says otherwise; it can
also be an existing Obsidian vault (everything Manifest writes lives under ``Manifest/``).

Safety: nothing is ever deleted. In files Manifest wrote, only the frontmatter and the block
between the ``manifest:begin``/``manifest:end`` markers are replaced, so your own writing
around them survives. A file at the same path without those markers is yours and is never
touched; the update goes to ``<name> (Manifest).md`` beside it instead. Paths are confined
to the vault folder.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BEGIN_PREFIX = "<!-- manifest:begin"
END = "<!-- manifest:end -->"
STATE = ".manifest-sync.json"
UNSAFE = re.compile(r'[\\/:*?"<>|#^\[\]\n\r\t]+')
README = """# Manifest vault

Your startup ideas, the plans Manifest made for them, and your own notes, as linked Markdown.
Open this folder in Obsidian (or any Markdown editor) and use Graph view to see how they connect.

- `Manifest/` is written by Manifest: ideas, documents, interviews and skills. Write freely
  outside the marked block in any file; the block itself is refreshed on every sync.
- `Notes/` is yours: notes your agent saved while you talked, linked to ideas with [[wiki-links]].

Your agent keeps it current with the Manifest plugin (`manifest_vault.py sync`).
"""


def vault_dir(arg: str | None) -> Path:
    raw = arg or os.environ.get("MANIFEST_VAULT") or str(Path.home() / "Manifest Vault")
    return Path(raw).expanduser().resolve()


def safe_name(text: str, fallback: str = "Untitled") -> str:
    name = UNSAFE.sub(" ", str(text or "")).strip().strip(".")
    return re.sub(r"\s+", " ", name)[:120] or fallback


def inside(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if root != target and root not in target.parents:
        raise SystemExit(f"refusing to write outside the vault: {relative}")
    return target


def ensure_folder(root: Path, folder: Path, readmes: bool) -> None:
    created = []
    for part in [folder, *folder.parents]:
        if part == root or root not in part.parents:
            break
        if not part.exists():
            created.append(part)
    folder.mkdir(parents=True, exist_ok=True)
    if readmes:
        for path in created:
            readme = path / "README.md"
            if not readme.exists():
                readme.write_text(
                    f"# {path.name}\n\nPart of your Manifest vault ({path.relative_to(root)}). "
                    "See the README at the vault root.\n",
                    encoding="utf-8",
                )


def split_generated(text: str) -> tuple[str, str, str, str] | None:
    """(frontmatter, before block, block, after block) for a Manifest-written file."""
    start = text.find(BEGIN_PREFIX)
    end = text.find(END)
    if start < 0 or end < start:
        return None
    front = ""
    body_start = 0
    if text.startswith("---\n"):
        close = text.find("\n---\n", 4)
        if 0 < close < start:
            front = text[: close + 5]
            body_start = close + 5
    return front, text[body_start:start], text[start : end + len(END)], text[end + len(END) :]


def merge(existing: str, incoming: str) -> str | None:
    """Replace frontmatter and generated block; keep the person's writing. None if not ours."""
    old = split_generated(existing)
    new = split_generated(incoming)
    if old is None or new is None:
        return None
    _, before, _, after = old
    front, _, block, _ = new
    return f"{front}{before}{block}{after}"


def write_file(root: Path, relative: str, content: str, readmes: bool) -> str:
    target = inside(root, relative)
    ensure_folder(root, target.parent, readmes)
    if not target.exists():
        extra = "\n## My notes\n\n" if '\ntype: "idea"\n' in content else ""
        target.write_text(content + extra, encoding="utf-8")
        return "created"
    existing = target.read_text(encoding="utf-8")
    merged = merge(existing, content)
    if merged is None:
        side = target.with_name(f"{target.stem} (Manifest){target.suffix}")
        side.write_text(content, encoding="utf-8")
        return f"kept yours; wrote {side.name}"
    if merged == existing:
        return "unchanged"
    target.write_text(merged, encoding="utf-8")
    return "updated"


def load_export(source: str) -> dict:
    raw = (
        sys.stdin.read()
        if source in ("-", "")
        else Path(source).expanduser().read_text(encoding="utf-8")
    )
    data = json.loads(raw)
    for key in ("structuredContent", "vaultExport"):
        if isinstance(data, dict) and key in data:
            data = data[key]
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        raise SystemExit(
            "expected the vault_export result: {generatedAt, files: [{path, content}]}"
        )
    return data


def cmd_sync(ns: argparse.Namespace) -> int:
    root = vault_dir(ns.vault)
    root.mkdir(parents=True, exist_ok=True)
    if not (root / "README.md").exists():
        (root / "README.md").write_text(README, encoding="utf-8")
    ensure_folder(root, root / "Notes", ns.folder_readmes)
    data = load_export(ns.source)
    counts: dict[str, int] = {}
    for item in data["files"]:
        result = write_file(root, str(item["path"]), str(item["content"]), ns.folder_readmes)
        key = result.split(";")[0]
        counts[key] = counts.get(key, 0) + 1
        if result.startswith("kept"):
            print(f"  {item['path']}: {result}")
    state = {
        "last_sync": data.get("generatedAt") or data.get("generated_at"),
        "files": len(data["files"]),
    }
    (root / STATE).write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
    summary = ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "nothing to write"
    print(f"Manifest vault at {root}: {summary}.")
    return 0


def cmd_note(ns: argparse.Namespace) -> int:
    root = vault_dir(ns.vault)
    text = sys.stdin.read() if ns.text in (None, "-") else ns.text
    text = (text or "").strip()
    if not text:
        raise SystemExit("the note is empty")
    now = datetime.now(timezone.utc).astimezone()
    title = safe_name(ns.title, "Note")
    folder = inside(root, "Notes")
    ensure_folder(root, folder, ns.folder_readmes)
    path = folder / f"{now:%Y-%m-%d} {title}.md"
    n = 2
    while path.exists():
        path = folder / f"{now:%Y-%m-%d} {title} {n}.md"
        n += 1
    ideas = [safe_name(i) for i in ns.idea or []]
    links = [f"[[Manifest/Ideas/{i}|{i}]]" for i in ideas]
    tags = ["note", *[re.sub(r"[^a-z0-9/-]+", "-", t.lower()).strip("-") for t in ns.tag or []]]
    front = ["---", 'type: "note"', f"created: \"{now.isoformat(timespec='seconds')}\""]
    if links:
        front += ["ideas:", *[f'  - "{link}"' for link in links]]
    front += ["tags:", *[f'  - "{t}"' for t in tags if t], "---"]
    body = [f"# {ns.title.strip()}", "", text]
    if links:
        body += ["", "Related: " + " · ".join(links)]
    path.write_text("\n".join(front + body) + "\n", encoding="utf-8")
    print(path)
    return 0


def cmd_since(ns: argparse.Namespace) -> int:
    state = vault_dir(ns.vault) / STATE
    if state.exists():
        print(json.loads(state.read_text(encoding="utf-8")).get("last_sync") or "")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--vault", help="vault folder (default: $MANIFEST_VAULT or ~/Manifest Vault)"
    )
    common.add_argument(
        "--folder-readmes", action="store_true", help="add a README.md to new folders"
    )
    sync = sub.add_parser(
        "sync", parents=[common], help="write a vault_export result into the vault"
    )
    sync.add_argument("source", nargs="?", default="-", help="JSON file, or - for stdin")
    note = sub.add_parser("note", parents=[common], help="save a note, linked to ideas")
    note.add_argument("--title", required=True)
    note.add_argument("--idea", action="append", help="title of a related idea (repeatable)")
    note.add_argument("--tag", action="append")
    note.add_argument("text", nargs="?", default="-", help="note text, or - for stdin")
    sub.add_parser("since", parents=[common], help="print the last sync time")
    sub.add_parser("where", parents=[common], help="print the vault folder")
    ns = parser.parse_args(argv)
    if ns.cmd == "where":
        print(vault_dir(ns.vault))
        return 0
    return {"sync": cmd_sync, "note": cmd_note, "since": cmd_since}[ns.cmd](ns)


if __name__ == "__main__":
    raise SystemExit(main())
