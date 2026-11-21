"""A tiny signed app for Manifest's background helpers on macOS.

macOS refuses plain background jobs (launchd running python) access to iCloud Drive
("Operation not permitted"), and the Manifest vault often lives there. Running the job
through an app bundle gives it an identity macOS can allow. The app's executable is a copy
of ``/usr/bin/env`` (ad-hoc signed), so ``<app> <program> <args…>`` runs the program in the
app's place, and no compiler is needed. The vault sync script has its own copy of this
(``manifest_vault.py``'s ``sync_app``) because it ships without dependencies.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

SUPPORT = Path.home() / "Library" / "Application Support" / "Manifest"


def _info(name: str, bundle_id: str, executable: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>{bundle_id}</string>
  <key>CFBundleName</key><string>{name}</string>
  <key>CFBundleExecutable</key><string>{executable}</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1</string>
  <key>LSBackgroundOnly</key><true/>
  <key>NSFileProviderDomainUsageDescription</key>
  <string>Manifest keeps your vault in iCloud Drive or another cloud folder up to date.</string>
</dict>
</plist>
"""


def launcher(name: str, bundle_id: str, base: Path | None = None) -> Path | None:
    """The app's executable, built once and kept (so a permission granted to it lasts),
    or None when it can't be built (then run the program directly)."""
    app = (base or SUPPORT) / f"{name}.app"
    executable = bundle_id.rsplit(".", 1)[-1]
    exe = app / "Contents" / "MacOS" / executable

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
        (app / "Contents" / "Info.plist").write_text(
            _info(name, bundle_id, executable), encoding="utf-8"
        )
        shutil.copyfile("/usr/bin/env", exe)  # contents only: env's system flags can't be copied
        exe.chmod(0o755)
    except OSError:
        return None
    return exe if codesign("--sign", "-", "--force") else None
