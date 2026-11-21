#!/usr/bin/env python3
"""Keep a local, Obsidian-style vault of your Manifest ideas, documents and notes, synced to your
account like iCloud Drive or OneDrive.

It needs only Python 3.9+ (standard library) and works offline; changes sync when you're back.

    manifest_vault.py login                       sign this computer in (browser approval)
    manifest_vault.py sync  [--full]              two-way sync with your account, now
    manifest_vault.py install                     keep syncing in the background (at login)
    manifest_vault.py status                      signed in? last sync, pending changes, service
    manifest_vault.py uninstall                   stop background sync (files stay)
    manifest_vault.py watch [--interval S]        run the sync loop in this terminal
    manifest_vault.py sync  EXPORT.json | -       write a vault_export result (agents, offline)
    manifest_vault.py note  --title T [--idea "Idea title" ...] [--tag t ...] [TEXT | -]
    manifest_vault.py since | where [--json]      last export time | the vault folder
    manifest_vault.py move  DEST [--json]         move the vault (``icloud``, ``documents``,
                                                  ``home`` or a path) and remember it
    manifest_vault.py icon                        give the vault folder the Manifest icon (macOS)

The vault folder is ``--vault``, else ``$MANIFEST_VAULT``, else the folder saved by ``move`` (in
``~/.config/manifest/vault.json``, shared with the ``manifest`` CLI, its bridge and the app), else
``~/Manifest Vault``. It can also be an existing Obsidian vault (everything Manifest writes lives
under ``Manifest/``).

What syncs: ``Manifest/`` comes down from your account. Your own files (``Notes/`` and any other
.md, .txt or .canvas file outside ``Manifest/``) and your writing around the generated block in
``Manifest/`` files go both ways. Hidden folders (``.obsidian``, ``.trash``) stay on this computer.

Safety: nothing is ever deleted. A file deleted on another computer moves to the vault's
``.trash/`` here. When the same file changed in two places, both are kept: the other version is
saved as ``<name> (conflicted copy <computer> <time>).md``. In files Manifest wrote, only the
frontmatter and the block between the ``manifest:begin``/``manifest:end`` markers are replaced; a
file without those markers is never overwritten by an export. Paths are confined to the vault.
If most synced files vanish at once (an unplugged drive), deletions are not sent to your account.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

VERSION = "2.0"
BEGIN_PREFIX = "<!-- manifest:begin"
END = "<!-- manifest:end -->"
OVERLAY_MARK = "<!-- manifest:generated -->"
STATE = ".manifest-sync.json"
LOCK = ".manifest-sync.lock"
UNSAFE = re.compile(r'[\\/:*?"<>|#^\[\]\n\r\t]+')
BAD_SEGMENT = re.compile(r'[\x00-\x1f\\:*?"<>|]')
EXTENSIONS = (".md", ".txt", ".canvas")
MAX_BYTES = 512 * 1024
DEFAULT_BASE_URL = "https://manifeststartup.com"
USER_AGENT = f"manifest-vault/{VERSION}"
CURSOR_OVERLAP = timedelta(minutes=2)
SERVICE_LABEL = "com.manifeststartup.vault-sync"
LOGO_PATH = "Manifest/Assets/Manifest logo.svg"
SNIPPET = "manifest"

# The Manifest mark (frontend/public/brand/manifest-mark.svg): the rising M on an ink tile.
LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="Manifest">
  <rect width="100" height="100" rx="23" fill="#1d1d1f"/>
  <path d="M25 78V35L50 60L75 26V78" fill="none" stroke="#fff" stroke-width="11" stroke-linejoin="miter" stroke-miterlimit="10"/>
</svg>
"""

# Obsidian CSS snippet: a calm, branded Home and tidy Manifest notes, in light and dark themes.
SNIPPET_CSS = """/* Manifest vault styling. Settings → Appearance → CSS snippets → "manifest". */
.manifest-home {
  --manifest-ink: #1d1d1f;
  --manifest-muted: #6e6e73;
}
.theme-dark .manifest-home {
  --manifest-ink: #f5f5f7;
  --manifest-muted: #a1a1a6;
}
.manifest-home .internal-embed.image-embed:first-of-type img,
.manifest-home img[alt$="Manifest logo.svg"] {
  border-radius: 16px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.12);
}
.manifest-home h1 {
  font-size: 2.4em;
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--manifest-ink);
  margin-bottom: 0.1em;
}
.manifest-home h2 {
  font-size: 0.8em;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--manifest-muted);
  border-bottom: 1px solid var(--background-modifier-border);
  padding-bottom: 0.3em;
  margin-top: 1.8em;
}
.callout[data-callout="manifest"] {
  --callout-color: 29, 29, 31;
  --callout-icon: lucide-cloud;
  border-radius: 12px;
}
.theme-dark .callout[data-callout="manifest"] {
  --callout-color: 245, 245, 247;
}
"""

README = """<img src="Manifest/Assets/Manifest logo.svg" width="72" alt="Manifest">

# Manifest vault

Your startup ideas, the plans Manifest made for them, and your own notes, as linked Markdown.
Open this folder in Obsidian (or any Markdown editor) and start at `Manifest/Home.md`; Graph view
shows how everything connects.

- `Manifest/` is written by Manifest: ideas, documents, interviews and skills. Write freely
  outside the marked block in any file; the block itself is refreshed on every sync.
- `Notes/` is yours: notes your agent saved while you talked, linked to ideas with [[wiki-links]].

It syncs with your Manifest account like iCloud Drive or OneDrive: your notes and your writing go
to every computer you sign in on. Set it up once with `manifest_vault.py login` and
`manifest_vault.py install`; `manifest_vault.py status` shows where things stand.
"""


class Offline(Exception):
    """Manifest can't be reached; changes wait on this computer."""


class SignedOut(Exception):
    """This computer needs to sign in again."""


# -- local vault ---------------------------------------------------------------------------


DEFAULT_VAULT_NAME = "Manifest Vault"
ICLOUD_DRIVE = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs"
# Places a person can name instead of a path ("move it to iCloud").
PLACES = {
    "icloud": ICLOUD_DRIVE,
    "icloud drive": ICLOUD_DRIVE,
    "documents": Path.home() / "Documents",
    "home": Path.home(),
}


def vault_setting_path() -> Path:
    """The saved vault folder, beside cli.json: ~/.config/manifest/vault.json."""
    return config_path().parent / "vault.json"


def saved_vault() -> str | None:
    try:
        data = json.loads(vault_setting_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    folder = data.get("folder") if isinstance(data, dict) else None
    return folder if isinstance(folder, str) and folder.strip() else None


def save_vault_setting(folder: Path) -> None:
    path = vault_setting_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"folder": str(folder)}, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def vault_source(arg: str | None) -> tuple[str, str]:
    """(folder, where it came from: flag, env, setting or default)."""
    if arg:
        return arg, "flag"
    if os.environ.get("MANIFEST_VAULT"):
        return os.environ["MANIFEST_VAULT"], "env"
    saved = saved_vault()
    if saved:
        return saved, "setting"
    return str(Path.home() / DEFAULT_VAULT_NAME), "default"


def vault_dir(arg: str | None) -> Path:
    return Path(vault_source(arg)[0]).expanduser().resolve()


def in_icloud(path: Path) -> bool:
    return path == ICLOUD_DRIVE.resolve() or ICLOUD_DRIVE.resolve() in path.parents


def safe_name(text: str, fallback: str = "Untitled") -> str:
    name = UNSAFE.sub(" ", str(text or "")).strip().strip(".")
    return re.sub(r"\s+", " ", name)[:120] or fallback


def inside(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if root != target and root not in target.parents:
        raise SystemExit(f"refusing to write outside the vault: {relative}")
    return target


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


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
        atomic_write(target, content + extra)
        return "created"
    existing = target.read_text(encoding="utf-8")
    merged = merge(existing, content)
    if merged is None:
        side = target.with_name(f"{target.stem} (Manifest){target.suffix}")
        atomic_write(side, content)
        return f"kept yours; wrote {side.name}"
    if merged == existing:
        return "unchanged"
    atomic_write(target, merged)
    return "updated"


# The folder icon (macOS): the system folder with the Manifest mark on it, the way Finder shows
# an app's iCloud folder (Obsidian, Pages). Drawn from the current system folder icon so it
# matches the macOS version and accent; Finder keeps it in the folder's hidden "Icon\r" file.
ICON_JS = r"""
ObjC.import('AppKit');
function run(argv) {
  const [svg, folder] = argv;
  const S = 1024;
  const base = $.NSWorkspace.sharedWorkspace.iconForFileType('public.folder');
  base.size = $.NSMakeSize(S, S);
  const mark = $.NSImage.alloc.initWithContentsOfFile(svg);
  if (!mark || mark.isNil()) return 'no-mark';
  const img = $.NSImage.alloc.initWithSize($.NSMakeSize(S, S));
  img.lockFocus;
  base.drawInRectFromRectOperationFraction($.NSMakeRect(0, 0, S, S), $.NSZeroRect,
    $.NSCompositingOperationSourceOver, 1);
  const m = S * 0.36;
  mark.drawInRectFromRectOperationFraction($.NSMakeRect((S - m) / 2, S * 0.29, m, m),
    $.NSZeroRect, $.NSCompositingOperationSourceOver, 1);
  img.unlockFocus;
  return $.NSWorkspace.sharedWorkspace.setIconForFileOptions(img, folder, 0) ? 'ok' : 'failed';
}
"""


def has_folder_icon(root: Path) -> bool:
    return (root / "Icon\r").exists()


def set_folder_icon(root: Path) -> bool:
    """Give the vault folder the Manifest icon. macOS only; False if it couldn't."""
    if platform.system() != "Darwin" or not root.is_dir() or not shutil.which("osascript"):
        return False
    import tempfile

    with tempfile.TemporaryDirectory(prefix="manifest-icon-") as tmp:
        svg, js = Path(tmp) / "mark.svg", Path(tmp) / "icon.js"
        svg.write_text(LOGO_SVG, encoding="utf-8")
        js.write_text(ICON_JS, encoding="utf-8")
        try:
            done = subprocess.run(
                ["osascript", "-l", "JavaScript", str(js), str(svg), str(root)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return False
    return done.returncode == 0 and done.stdout.strip() == "ok"


def ensure_branding(root: Path) -> None:
    """The Manifest logo beside Home.md, the root README, the folder icon (macOS) and an
    Obsidian snippet that styles Home. Each is written once; edits and a disabled snippet
    are respected."""
    root.mkdir(parents=True, exist_ok=True)
    if not has_folder_icon(root):
        set_folder_icon(root)
    if not (root / "README.md").exists():
        atomic_write(root / "README.md", README)
    logo = root / LOGO_PATH
    if not logo.exists():
        atomic_write(logo, LOGO_SVG)
    obsidian = root / ".obsidian"
    snippet = obsidian / "snippets" / f"{SNIPPET}.css"
    if snippet.exists():
        return
    atomic_write(snippet, SNIPPET_CSS)
    appearance = obsidian / "appearance.json"
    try:
        settings = json.loads(appearance.read_text(encoding="utf-8")) if appearance.exists() else {}
    except (OSError, ValueError):
        return  # unreadable settings are the person's; leave them alone
    if isinstance(settings, dict):
        enabled = list(settings.get("enabledCssSnippets") or [])
        if SNIPPET not in enabled:
            settings["enabledCssSnippets"] = [*enabled, SNIPPET]
            atomic_write(appearance, json.dumps(settings, indent=2) + "\n")


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


def load_state(root: Path) -> dict[str, Any]:
    try:
        state = json.loads((root / STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def save_state(root: Path, state: dict[str, Any]) -> None:
    atomic_write(root / STATE, json.dumps(state, indent=1, sort_keys=True) + "\n")


def apply_export(root: Path, data: dict, readmes: bool, out=sys.stdout) -> dict[str, int]:
    ensure_branding(root)
    ensure_folder(root, root / "Notes", readmes)
    counts: dict[str, int] = {}
    for item in data["files"]:
        result = write_file(root, str(item["path"]), str(item["content"]), readmes)
        key = result.split(";")[0]
        counts[key] = counts.get(key, 0) + 1
        if result.startswith("kept"):
            print(f"  {item['path']}: {result}", file=out)
    return counts


# -- what syncs ----------------------------------------------------------------------------


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def syncable(rel: str) -> bool:
    parts = rel.split("/")
    if not rel.lower().endswith(EXTENSIONS) or len(rel) > 400:
        return False
    return all(p and not p.startswith(".") and not BAD_SEGMENT.search(p) for p in parts)


def overlay_of(text: str) -> str | None:
    """The person's writing around a generated block, or None if the file isn't Manifest's."""
    parts = split_generated(text)
    if parts is None:
        return None
    _, before, _, after = parts
    return f"{before}{OVERLAY_MARK}{after}"


def trivial_overlay(overlay: str) -> bool:
    before, _, after = overlay.partition(OVERLAY_MARK)
    return not before.strip() and after.strip() in ("", "## My notes")


def local_files(root: Path) -> dict[str, tuple[str, str]]:
    """{path: (kind, text to sync)}; kind is "file" or "overlay" (Manifest/ files)."""
    found: dict[str, tuple[str, str]] = {}
    if not root.is_dir():
        return found
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if not syncable(rel):
                continue
            try:
                if path.stat().st_size > MAX_BYTES:
                    continue
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if rel.startswith("Manifest/"):
                overlay = overlay_of(text)
                if overlay is not None:
                    found[rel] = ("overlay", overlay)
                elif not path.stem.endswith(" (Manifest)"):
                    found[rel] = ("file", text)
            else:
                found[rel] = ("file", text)
    return found


def local_signature(root: Path) -> tuple:
    """Cheap fingerprint (paths, sizes, mtimes) to notice edits without reading files."""
    items = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if name.lower().endswith(EXTENSIONS):
                try:
                    st = (Path(dirpath) / name).stat()
                except OSError:
                    continue
                items.append((dirpath, name, st.st_size, st.st_mtime_ns))
    return tuple(sorted(items))


def apply_overlay(root: Path, rel: str, overlay: str) -> bool:
    path = inside(root, rel)
    if not path.exists():
        return False  # the export hasn't written it yet; try again next sync
    parts = split_generated(path.read_text(encoding="utf-8"))
    if parts is None:
        return False
    front, _, block, _ = parts
    before, _, after = overlay.partition(OVERLAY_MARK)
    atomic_write(path, f"{front}{before}{block}{after}")
    return True


def to_trash(root: Path, rel: str) -> Path | None:
    path = inside(root, rel)
    if not path.exists():
        return None
    target = root / ".trash" / rel
    n = 2
    while target.exists():
        target = root / ".trash" / f"{Path(rel).with_suffix('')} {n}{Path(rel).suffix}"
        n += 1
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(target))
    return target


def conflicted_copy(root: Path, rel: str, kind: str, text: str) -> str:
    """Save this computer's version beside the account's; returns its vault path."""
    stamp = datetime.now().strftime("%Y-%m-%d %H%M")
    host = safe_name(socket.gethostname().split(".")[0], "this computer")
    p = Path(rel)
    if kind == "overlay":  # your writing from a Manifest file goes to Notes/
        before, _, after = text.partition(OVERLAY_MARK)
        text = f"# {p.stem}\n\nFrom [[{rel[:-3]}|{p.stem}]] on {host}:\n\n{before.strip()}\n\n{after.strip()}\n"
        p = Path("Notes/Conflicts") / p.name
    name = f"{p.stem} (conflicted copy {host} {stamp}){p.suffix}"
    out = p.with_name(name).as_posix()
    n = 2
    while (root / out).exists():
        out = p.with_name(f"{p.stem} (conflicted copy {host} {stamp} {n}){p.suffix}").as_posix()
        n += 1
    atomic_write(inside(root, out), text)
    return out


# -- account -------------------------------------------------------------------------------


def config_path() -> Path:
    """Shared with the `manifest` CLI: ~/.config/manifest/cli.json (mode 0600)."""
    explicit = os.environ.get("MANIFEST_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base).expanduser() / "manifest" / "cli.json"


def load_config() -> dict[str, Any]:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(data: dict[str, Any]) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp, path)
    return path


def base_url(override: str | None = None) -> str:
    value = override or os.environ.get("MANIFEST_API_URL") or load_config().get("base_url")
    return str(value or DEFAULT_BASE_URL).rstrip("/")


def token() -> str | None:
    return os.environ.get("MANIFEST_API_TOKEN") or load_config().get("token") or None


def http_json(url: str, body: dict | None, auth: str | None = None, timeout: float = 30) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", USER_AGENT)
    if data:
        req.add_header("Content-Type", "application/json")
    if auth:
        req.add_header("Authorization", f"Bearer {auth}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise SignedOut("Manifest signed this computer out.") from None
        if exc.code >= 500 or exc.code == 429:
            raise Offline(f"Manifest is busy (HTTP {exc.code}).") from None
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise SystemExit(f"Manifest refused the request (HTTP {exc.code}): {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Offline(f"Can't reach Manifest ({getattr(exc, 'reason', exc)}).") from None


class Account:
    """GraphQL calls as the signed-in person."""

    def __init__(self, url: str, auth: str, post: Callable[..., dict] = http_json):
        self.url, self.auth, self.post = url, auth, post

    def graphql(self, document: str, variables: dict) -> dict:
        body = self.post(
            f"{self.url}/graphql", {"query": document, "variables": variables}, self.auth
        )
        errors = body.get("errors") or []
        if errors:
            message = "; ".join(str(e.get("message", e)) for e in errors if isinstance(e, dict))
            low = message.lower()
            if any(
                w in low for w in ("token", "expired", "authenticat", "forbidden", "permission")
            ):
                raise SignedOut(message)
            raise SystemExit(f"Manifest: {message}")
        return body.get("data") or {}

    def export(self, since: str | None) -> dict:
        q = "query($s:String){vaultExport(sinceUpdatedAt:$s){generatedAt files{path content}}}"
        return self.graphql(q, {"s": since})["vaultExport"]

    def files(self, since: str | None) -> dict:
        q = (
            "query($s:String){vaultFiles(sinceUpdatedAt:$s)"
            "{serverTime files{path content sha256 deleted device}}}"
        )
        return self.graphql(q, {"s": since})["vaultFiles"]

    def put(self, path: str, content: str | None, base: str | None) -> dict:
        q = (
            "mutation($p:String!,$c:String,$b:String,$d:Boolean!,$v:String)"
            "{putVaultFile(path:$p,content:$c,baseSha256:$b,delete:$d,device:$v)"
            "{status file{path content sha256 deleted}}}"
        )
        variables = {
            "p": path,
            "c": content,
            "b": base,
            "d": content is None,
            "v": socket.gethostname(),
        }
        return self.graphql(q, variables)["putVaultFile"]


def account() -> Account:
    auth = token()
    if not auth:
        raise SignedOut("This computer isn't signed in to Manifest.")
    return Account(base_url(), auth)


# -- two-way sync --------------------------------------------------------------------------


def _record(state: dict, rel: str, digest: str | None) -> None:
    synced = state.setdefault("synced", {})
    if digest is None:
        synced.pop(rel, None)
    else:
        synced[rel] = digest


def take_theirs(root: Path, rel: str, kind: str, theirs: dict, state: dict) -> bool:
    """Write the account's version of a file (or of your writing in a Manifest file)."""
    text = theirs.get("content") or ""
    if kind == "overlay":
        if not apply_overlay(root, rel, text):
            return False
    else:
        atomic_write(inside(root, rel), text)
    _record(state, rel, theirs.get("sha256") or sha256(text))
    return True


def pull_files(root: Path, acct: Account, state: dict, report: list[str]) -> None:
    cursor = state.get("cursor")
    since = None
    if cursor:
        try:
            since = (datetime.fromisoformat(cursor) - CURSOR_OVERLAP).isoformat()
        except ValueError:
            since = None
    page = acct.files(since)
    synced = state.setdefault("synced", {})
    local = local_files(root)
    for remote in page.get("files") or []:
        rel = remote["path"]
        if not syncable(rel):
            continue
        base = synced.get(rel)
        mine = local.get(rel)
        mine_sha = sha256(mine[1]) if mine else None
        if remote.get("deleted"):
            # Unchanged here: move it to .trash. Edited here: keep it; it uploads as new.
            if mine and mine_sha == base and mine[0] == "file":
                to_trash(root, rel)
                report.append(f"moved to .trash (deleted on another computer): {rel}")
            _record(state, rel, None)
            continue
        theirs = remote.get("content") or ""
        overlay = rel.startswith("Manifest/") and OVERLAY_MARK in theirs
        kind = "overlay" if overlay else "file"
        theirs_sha = remote.get("sha256") or sha256(theirs)
        if mine_sha == theirs_sha:
            _record(state, rel, theirs_sha)
            continue
        if base == theirs_sha:
            continue  # unchanged in the account; any edit or deletion here goes up in the push
        if mine is not None and mine_sha != base:
            copy = conflicted_copy(root, rel, mine[0], mine[1])
            report.append(f"conflict: kept both, yours is {copy}")
        if take_theirs(root, rel, kind, {"content": theirs, "sha256": theirs_sha}, state):
            report.append(f"updated your notes in {rel}" if overlay else f"downloaded {rel}")
    state["cursor"] = page.get("serverTime") or state.get("cursor")


def pending_changes(root: Path, state: dict) -> tuple[dict[str, tuple[str, str]], list[str]]:
    synced = state.get("synced") or {}
    local = local_files(root)
    changed = {
        rel: item
        for rel, item in local.items()
        if sha256(item[1]) != synced.get(rel)
        and not (item[0] == "overlay" and rel not in synced and trivial_overlay(item[1]))
    }
    gone = [rel for rel in synced if rel not in local and not rel.startswith("Manifest/")]
    return changed, gone


def push_files(root: Path, acct: Account, state: dict, report: list[str]) -> None:
    changed, gone = pending_changes(root, state)
    synced = state.setdefault("synced", {})
    if len(gone) > 20 and len(gone) > len(synced) // 2 and not state.get("allow_mass_delete"):
        report.append(
            f"{len(gone)} synced files are missing here, so no deletions were sent. "
            "If you meant to delete them, run `manifest_vault.py sync --allow-mass-delete`."
        )
        gone = []
    for rel in sorted(changed):
        kind, text = changed[rel]
        result = acct.put(rel, text, synced.get(rel))
        status, theirs = result.get("status"), result.get("file") or {}
        if status in ("saved", "unchanged"):
            _record(state, rel, sha256(text))
            if status == "saved":
                report.append(f"uploaded {rel}")
        elif theirs.get("deleted"):  # deleted elsewhere, edited here: yours uploads as new
            _record(state, rel, None)
        else:  # changed in both places: keep both
            copy = conflicted_copy(root, rel, kind, text)
            report.append(f"conflict: kept both, yours is {copy}")
            take_theirs(root, rel, kind, theirs, state)
    for rel in gone:
        result = acct.put(rel, None, synced.get(rel))
        if result.get("status") == "conflict":
            theirs = result.get("file") or {}
            if not theirs.get("deleted"):  # changed elsewhere after you deleted it: restore
                take_theirs(root, rel, "file", theirs, state)
                report.append(f"restored {rel} (it changed on another computer)")
                continue
        _record(state, rel, None)
        report.append(f"deleted from your account: {rel}")


def sync_online(
    root: Path,
    acct: Account,
    *,
    export: bool = True,
    full: bool = False,
    readmes: bool = False,
    allow_mass_delete: bool = False,
) -> list[str]:
    """One full cycle: Manifest/ down, your files down, your changes up."""
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    state = load_state(root)
    if not isinstance(state.get("synced"), dict):
        state["synced"] = {}
    report: list[str] = []
    try:
        if export:
            data = acct.export(None if full else state.get("last_sync"))
            counts = apply_export(root, data, readmes, out=sys.stderr)
            changed = sum(n for k, n in counts.items() if k != "unchanged")
            if changed:
                report.append(
                    f"Manifest: {', '.join(f'{n} {k}' for k, n in sorted(counts.items()) if k != 'unchanged')}"
                )
            state["last_sync"] = data.get("generatedAt") or state.get("last_sync")
        else:
            ensure_branding(root)
        if full:
            state.pop("cursor", None)
        pull_files(root, acct, state, report)
        state["allow_mass_delete"] = allow_mass_delete
        push_files(root, acct, state, report)
        state.pop("allow_mass_delete", None)
        state.update(status="up to date", error=None, checked_at=_now())
    except Offline as exc:
        state.update(status="offline", error=str(exc), checked_at=_now())
        raise
    except SignedOut as exc:
        state.update(status="signed out", error=str(exc), checked_at=_now())
        raise
    finally:
        state.pop("allow_mass_delete", None)
        save_state(root, state)
    return report


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class VaultLock:
    """One sync at a time per vault (the background service and a manual sync)."""

    def __init__(self, root: Path, wait: float = 60):
        self.path, self.wait, self.handle = root / LOCK, wait, None

    def __enter__(self) -> VaultLock:
        try:
            import fcntl
        except ImportError:  # Windows: no advisory locks; syncs are short
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "w")
        deadline = time.monotonic() + self.wait
        while True:
            try:
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.monotonic() > deadline:
                    raise SystemExit(
                        "Another sync of this vault is running; try again shortly."
                    ) from None
                time.sleep(0.5)

    def __exit__(self, *exc: Any) -> None:
        if self.handle:
            self.handle.close()


def notify(message: str) -> None:
    if platform.system() == "Darwin":
        script = f'display notification {json.dumps(message)} with title "Manifest vault"'
        subprocess.run(["osascript", "-e", script], capture_output=True, check=False)


# -- commands ------------------------------------------------------------------------------


def cmd_sync(ns: argparse.Namespace) -> int:
    root = vault_dir(ns.vault)
    if ns.source is not None:  # an agent's vault_export result: offline, one way
        root.mkdir(parents=True, exist_ok=True)
        data = load_export(ns.source)
        counts = apply_export(root, data, ns.folder_readmes)
        state = load_state(root)
        state["last_sync"] = data.get("generatedAt") or data.get("generated_at")
        save_state(root, state)
        summary = ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "nothing to write"
        print(f"Manifest vault at {root}: {summary}.")
        return 0
    try:
        with VaultLock(root):
            report = sync_online(
                root,
                account(),
                full=ns.full,
                readmes=ns.folder_readmes,
                allow_mass_delete=ns.allow_mass_delete,
            )
    except SignedOut as exc:
        print(f"{exc} Run `manifest_vault.py login`.", file=sys.stderr)
        return 2
    except Offline as exc:
        print(
            f"{exc} Your changes are safe here and sync when you're back online.", file=sys.stderr
        )
        return 3
    for line in report:
        print(f"  {line}")
    print(f"Manifest vault at {root} is up to date.")
    return 0


def cmd_watch(ns: argparse.Namespace) -> int:
    """The background loop: export every few minutes, your files every `interval` seconds,
    and local edits within seconds. Offline or signed out, it waits and retries."""
    root = vault_dir(ns.vault)
    acct_interval, export_interval = max(10, ns.interval), max(60, ns.interval * 10)
    next_export = next_files = 0.0
    signature: tuple = ()
    told_signed_out = False
    print(f"Syncing {root} with {base_url()} (Ctrl-C to stop).", flush=True)
    while True:
        now = time.monotonic()
        current = local_signature(root) if root.is_dir() else ()
        edited = current != signature
        if edited or now >= next_files:
            try:
                with VaultLock(root, wait=5):
                    report = sync_online(root, account(), export=now >= next_export)
                if now >= next_export:
                    next_export = now + export_interval
                next_files = now + acct_interval
                told_signed_out = False
                for line in report:
                    print(f"{_now()} {line}", flush=True)
                signature = local_signature(root)
            except Offline as exc:
                print(f"{_now()} offline: {exc}", flush=True)
                next_files = now + 60
                signature = current
            except SignedOut as exc:
                if not told_signed_out:
                    print(f"{_now()} signed out: {exc}", flush=True)
                    notify("Sign in again to keep your vault in sync: manifest_vault.py login")
                    told_signed_out = True
                next_files = now + 300
                signature = current
            except SystemExit as exc:
                print(f"{_now()} error: {exc}", flush=True)
                next_files = now + 120
                signature = current
        if ns.once:
            return 0
        time.sleep(3)


LOGIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Manifest vault</title></head>
<body style="font-family:system-ui,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0">
<main style="max-width:26rem;text-align:center;padding:1rem">{logo}<h1 style="letter-spacing:-.03em">{title}</h1>
<p style="color:#6e6e73">{message}</p></main></body></html>"""


def cmd_login(ns: argparse.Namespace) -> int:
    """Approve this computer in the browser (loopback redirect + PKCE, ADR 0003); the session
    is shared with the `manifest` CLI and shows under Account → Security → Active sessions."""
    url = base_url(ns.base_url)
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    state_value = secrets.token_urlsafe(24)
    result: dict[str, str] = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parts = urlsplit(self.path)
            if parts.path != "/callback":
                self.send_error(404)
                return
            params = {k: v[0] for k, v in parse_qs(parts.query).items()}
            ok = "code" in params and "error" not in params
            page = LOGIN_PAGE.format(
                logo=LOGO_SVG.replace("<svg ", '<svg width="64" height="64" '),
                title="Your vault is connected" if ok else "Not signed in",
                message="You can close this tab." if ok else "Return to your terminal.",
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(page)
            if not result:
                result.update(params)
                done.set()

        def log_message(self, *args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    redirect = f"http://127.0.0.1:{server.server_address[1]}/callback"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    query = urlencode(
        {
            "redirect_uri": redirect,
            "state": state_value,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    approve = f"{url}/api/cli/authorize?{query}"
    print(f"Approve this computer in your browser. If it doesn't open, visit:\n  {approve}")
    if not ns.no_browser:
        webbrowser.open(approve)
    try:
        if not done.wait(300):
            raise SystemExit("Timed out waiting for the browser; run login again.")
    finally:
        server.shutdown()
        server.server_close()
    if result.get("state") != state_value:
        raise SystemExit("The browser returned a different state; refusing to continue.")
    if result.get("error") or not result.get("code"):
        raise SystemExit(f"Not signed in: {result.get('error') or 'no code returned'}.")
    grant = http_json(
        f"{url}/api/cli/token",
        {
            "code": result["code"],
            "code_verifier": verifier,
            "redirect_uri": redirect,
            "hostname": socket.gethostname(),
        },
    )
    saved = load_config()
    saved.update(
        base_url=url,
        token=grant["access_token"],
        expires_at=grant.get("expires_at"),
        label=grant.get("label"),
        user=grant.get("user") or {},
    )
    save_config(saved)
    who = (grant.get("user") or {}).get("email") or "your account"
    print(f"Signed in as {who}. Next: `manifest_vault.py sync`, then `manifest_vault.py install`.")
    return 0


def _service_paths() -> tuple[Path, Path, Path]:
    """(installed script, service file, log) for this OS."""
    home = Path.home()
    if platform.system() == "Darwin":
        return (
            home / "Library/Application Support/Manifest/manifest_vault.py",
            home / f"Library/LaunchAgents/{SERVICE_LABEL}.plist",
            home / "Library/Logs/Manifest/vault-sync.log",
        )
    data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    return (
        data / "manifest-vault/manifest_vault.py",
        config / "systemd/user/manifest-vault-sync.service",
        data / "manifest-vault/vault-sync.log",
    )


APP_NAME = "Manifest Vault Sync"
APP_INFO = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>{SERVICE_LABEL}</string>
  <key>CFBundleName</key><string>{APP_NAME}</string>
  <key>CFBundleExecutable</key><string>manifest-vault-sync</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1</string>
  <key>LSBackgroundOnly</key><true/>
  <key>NSFileProviderDomainUsageDescription</key>
  <string>Manifest keeps your vault in sync when it's in iCloud Drive or another cloud folder.</string>
</dict>
</plist>
"""


def sync_app(base: Path) -> Path | None:
    """macOS: a tiny signed app that background sync runs through, so it may use a vault in
    iCloud Drive (macOS blocks plain background jobs there with "Operation not permitted").
    Its executable is a copy of /usr/bin/env, so no compiler is needed. Built once and kept,
    so a permission the person grants stays valid. None if it can't be built."""
    app = base / f"{APP_NAME}.app"
    exe = app / "Contents/MacOS/manifest-vault-sync"

    def codesign(*args: str) -> bool:
        try:
            done = subprocess.run(["codesign", *args, str(app)], capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return False
        return done.returncode == 0

    if exe.exists() and codesign("--verify"):
        return exe
    try:
        exe.parent.mkdir(parents=True, exist_ok=True)
        (app / "Contents/Info.plist").write_text(APP_INFO, encoding="utf-8")
        shutil.copyfile("/usr/bin/env", exe)  # contents only: env's system flags can't be copied
        exe.chmod(0o755)
    except OSError:
        return None
    return exe if codesign("--sign", "-", "--force") else None


def _plist(python: str, script: Path, root: Path, log: Path, launcher: Path | None = None) -> str:
    program = ([str(launcher)] if launcher else []) + [python, str(script)]
    args = "".join(f"\n    <string>{a}</string>" for a in (*program, "watch", "--vault", str(root)))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{SERVICE_LABEL}</string>
  <key>ProgramArguments</key>
  <array>{args}
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ProcessType</key>
  <string>Background</string>
  <key>StandardOutPath</key>
  <string>{log}</string>
  <key>StandardErrorPath</key>
  <string>{log}</string>
</dict>
</plist>
"""


def cmd_install(ns: argparse.Namespace) -> int:
    root = vault_dir(ns.vault)
    if not token():
        raise SystemExit("Sign in first: `manifest_vault.py login`.")
    _install_service(root)
    return 0


def _install_service(root: Path) -> None:
    script, service, log = _service_paths()
    script.parent.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve()
    if here != script.resolve():  # already running the installed copy (a move from the app)
        shutil.copy2(here, script)  # survives plugin updates and cache clears
    system = platform.system()
    if system == "Darwin":
        service.parent.mkdir(parents=True, exist_ok=True)
        launcher = sync_app(script.parent)
        service.write_text(_plist(sys.executable, script, root, log, launcher), encoding="utf-8")
        domain = f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "bootout", f"{domain}/{SERVICE_LABEL}"], capture_output=True)
        subprocess.run(["launchctl", "bootstrap", domain, str(service)], check=True)
    elif system == "Linux":
        service.parent.mkdir(parents=True, exist_ok=True)
        service.write_text(
            "[Unit]\nDescription=Manifest vault sync\n\n[Service]\n"
            f'ExecStart="{sys.executable}" "{script}" watch --vault "{root}"\n'
            "Restart=always\nRestartSec=30\n\n[Install]\nWantedBy=default.target\n",
            encoding="utf-8",
        )
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", "manifest-vault-sync.service"], check=True
        )
    else:
        raise SystemExit(
            "Background sync installs on macOS and Linux. On Windows, add a Task Scheduler task "
            f'at log-on that runs: "{sys.executable}" "{script}" watch --vault "{root}"'
        )
    print(f"Background sync is on for {root}. It starts at login; log: {log}")


def _stop_service() -> None:
    if platform.system() == "Darwin":
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/{SERVICE_LABEL}"], capture_output=True
        )
        # bootout returns before the process is gone; wait so it can't write mid-move.
        for _ in range(50):
            out = subprocess.run(
                ["launchctl", "print", f"gui/{os.getuid()}/{SERVICE_LABEL}"],
                capture_output=True,
            )
            if out.returncode != 0:
                break
            time.sleep(0.1)
    elif platform.system() == "Linux":
        subprocess.run(
            ["systemctl", "--user", "stop", "manifest-vault-sync.service"], capture_output=True
        )


def move_target(dest: str, current: Path) -> Path:
    """Where `move DEST` puts the vault. A named place or an existing folder gets the vault
    inside it (like `mv`); any other path is the new vault folder itself."""
    place = PLACES.get(dest.strip().lower())
    if place is not None:
        return (place / current.name).resolve()
    target = Path(dest).expanduser()
    if not target.is_absolute():
        raise SystemExit("Give the new place as a full path, or icloud, documents or home.")
    target = target.resolve()
    if target.is_dir() and target != current and not (target / LOGO_PATH).exists():
        return target / current.name
    return target


def move_vault(current: Path, target: Path) -> dict[str, Any]:
    """Move the vault folder and remember it. Never overwrites or deletes anything."""
    if target == current:
        save_vault_setting(target)
        return {"folder": str(target), "moved": False, "note": "already there"}
    if current in target.parents:
        raise SystemExit("The new place can't be inside the vault itself.")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise SystemExit(f"{target} already exists and isn't empty; choose another place.")
    if not target.parent.is_dir():
        raise SystemExit(f"{target.parent} doesn't exist.")
    _, service, _ = _service_paths()
    background = service.exists()
    if background:
        _stop_service()
    moved = False
    try:
        if current.is_dir():
            if target.exists():
                target.rmdir()  # empty (checked above)
            shutil.move(str(current), str(target))
            moved = True
        else:
            target.mkdir(parents=True, exist_ok=True)
        save_vault_setting(target)
    finally:
        if background:  # restart on the new folder, or on the old one if the move failed
            _install_service(target if moved or not current.is_dir() else current)
    icon = set_folder_icon(target)
    return {"folder": str(target), "from": str(current), "moved": moved, "icon": icon}


def cmd_move(ns: argparse.Namespace) -> int:
    current = vault_dir(ns.vault)
    target = move_target(ns.dest, current)
    result = move_vault(current, target)
    if (
        os.environ.get("MANIFEST_VAULT")
        and Path(os.environ["MANIFEST_VAULT"]).expanduser().resolve() != target
    ):
        result["warning"] = (
            "MANIFEST_VAULT is set in this shell and still points at the old folder; remove it."
        )
    if ns.json:
        print(json.dumps(result))
    else:
        if result.get("moved"):
            print(f"Moved your vault to {result['folder']}.")
        elif result.get("note"):
            print(f"Your vault is already at {result['folder']}.")
        else:
            print(f"Your vault will live at {result['folder']}.")
        if result.get("warning"):
            print(result["warning"])
    return 0


def cmd_where(ns: argparse.Namespace) -> int:
    raw, source = vault_source(ns.vault)
    root = Path(raw).expanduser().resolve()
    if not ns.json:
        print(root)
        return 0
    _, service, _ = _service_paths()
    print(
        json.dumps(
            {
                "folder": str(root),
                "source": source,
                "exists": root.is_dir(),
                "icloud": in_icloud(root),
                "icloud_available": ICLOUD_DRIVE.is_dir(),
                "background_sync": service.exists(),
                "places": {
                    k: str(v) for k, v in PLACES.items() if k != "icloud drive" and v.is_dir()
                },
            }
        )
    )
    return 0


def cmd_icon(ns: argparse.Namespace) -> int:
    root = vault_dir(ns.vault)
    ok = set_folder_icon(root)
    print(
        "The vault folder has the Manifest icon." if ok else "Couldn't set the icon (macOS only)."
    )
    return 0 if ok else 1


def cmd_uninstall(ns: argparse.Namespace) -> int:
    _, service, _ = _service_paths()
    if platform.system() == "Darwin":
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/{SERVICE_LABEL}"], capture_output=True
        )
    elif platform.system() == "Linux":
        subprocess.run(
            ["systemctl", "--user", "disable", "--now", "manifest-vault-sync.service"],
            capture_output=True,
        )
    if service.exists():
        service.unlink()  # our own service file; the vault and its files are untouched
    print("Background sync is off. Your vault stays where it is.")
    return 0


def _service_running() -> str:
    _, service, _ = _service_paths()
    if not service.exists():
        return "off (run `manifest_vault.py install`)"
    if platform.system() == "Darwin":
        out = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{SERVICE_LABEL}"],
            capture_output=True,
            text=True,
        ).stdout
        return "running" if "state = running" in out else "installed, not running"
    return "installed"


def cmd_status(ns: argparse.Namespace) -> int:
    root = vault_dir(ns.vault)
    state = load_state(root)
    cfg = load_config()
    who = (cfg.get("user") or {}).get("email") if token() else None
    changed, gone = pending_changes(root, state) if root.is_dir() else ({}, [])
    print(f"Vault:       {root}")
    print(f"Account:     {who or 'not signed in'}{f' ({base_url()})' if who else ''}")
    print(f"Status:      {state.get('status') or 'not synced yet'}")
    if state.get("error"):
        print(f"Last issue:  {state['error']}")
    print(f"Last check:  {state.get('checked_at') or '-'}")
    print(f"Synced:      {len(state.get('synced') or {})} of your files")
    print(f"Pending:     {len(changed)} to upload, {len(gone)} deletions")
    print(f"Background:  {_service_running()}")
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
    print(load_state(vault_dir(ns.vault)).get("last_sync") or "")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--vault",
        help="vault folder (default: $MANIFEST_VAULT, the saved folder, or ~/Manifest Vault)",
    )
    common.add_argument(
        "--folder-readmes", action="store_true", help="add a README.md to new folders"
    )
    sync = sub.add_parser("sync", parents=[common], help="two-way sync now (or write an export)")
    sync.add_argument(
        "source", nargs="?", default=None, help="a vault_export JSON file, or - for stdin"
    )
    sync.add_argument("--full", action="store_true", help="re-read everything from the account")
    sync.add_argument(
        "--allow-mass-delete",
        action="store_true",
        help="send deletions even if most files vanished",
    )
    watch = sub.add_parser("watch", parents=[common], help="keep syncing (the background service)")
    watch.add_argument("--interval", type=int, default=30, help="seconds between account checks")
    watch.add_argument("--once", action="store_true", help=argparse.SUPPRESS)
    login = sub.add_parser("login", parents=[common], help="sign this computer in to Manifest")
    login.add_argument("--base-url", help=f"Manifest address (default {DEFAULT_BASE_URL})")
    login.add_argument("--no-browser", action="store_true", help="print the URL only")
    sub.add_parser("install", parents=[common], help="sync in the background at login")
    sub.add_parser("uninstall", parents=[common], help="stop background sync")
    sub.add_parser("status", parents=[common], help="show sync status")
    note = sub.add_parser("note", parents=[common], help="save a note, linked to ideas")
    note.add_argument("--title", required=True)
    note.add_argument("--idea", action="append", help="title of a related idea (repeatable)")
    note.add_argument("--tag", action="append")
    note.add_argument("text", nargs="?", default="-", help="note text, or - for stdin")
    sub.add_parser("since", parents=[common], help="print the last export time")
    where = sub.add_parser("where", parents=[common], help="print the vault folder")
    where.add_argument("--json", action="store_true", help="folder, source and places as JSON")
    move = sub.add_parser("move", parents=[common], help="move the vault folder and remember it")
    move.add_argument("dest", help="icloud, documents, home, or a full path")
    move.add_argument("--json", action="store_true")
    sub.add_parser("icon", parents=[common], help="give the vault folder the Manifest icon")
    ns = parser.parse_args(argv)
    commands = {
        "where": cmd_where,
        "move": cmd_move,
        "icon": cmd_icon,
        "sync": cmd_sync,
        "watch": cmd_watch,
        "login": cmd_login,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "status": cmd_status,
        "note": cmd_note,
        "since": cmd_since,
    }
    return commands[ns.cmd](ns)


if __name__ == "__main__":
    raise SystemExit(main())
