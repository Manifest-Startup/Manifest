"""HTTPS for the bridge, so Safari can reach it too.

Safari blocks a secure page (https://manifeststartup.com) from calling ``http://127.0.0.1``
or ``http://localhost`` (mixed content), while Chrome allows it. So the bridge also serves
``https://127.0.0.1:47823`` with a certificate this Mac trusts:

- A one-off certificate authority is made, limited by name constraints to ``127.0.0.1``
  and ``localhost``. It signs the bridge's certificate, and then its private key is
  deleted, so it can never sign anything again.
- ``manifest bridge --install`` asks macOS to trust it, in the login keychain, for TLS
  only. macOS asks for the person's password or Touch ID once.
- The certificate lasts 800 days (Apple's limit is 825). Running the setup again renews it.

Uses the system ``openssl``, so it adds no dependency. Files are in ``~/Library/Application
Support/Manifest/bridge-tls`` and are readable only by this user.
"""

from __future__ import annotations

import os
import shutil
import ssl
import subprocess
import tempfile
import time
from pathlib import Path

HTTPS_PORT = 47823
DAYS = 800
RENEW_BEFORE_SECONDS = 30 * 24 * 3600
CA_NAME = "Manifest Bridge (127.0.0.1 only)"

_CA_CONFIG = f"""[req]
distinguished_name = dn
x509_extensions = v3_ca
prompt = no
[dn]
CN = {CA_NAME}
O = Manifest
[v3_ca]
basicConstraints = critical,CA:TRUE,pathlen:0
keyUsage = critical,keyCertSign,cRLSign
nameConstraints = critical,permitted;IP:127.0.0.1/255.255.255.255,permitted;DNS:localhost
subjectKeyIdentifier = hash
"""

_LEAF_EXT = """basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = IP:127.0.0.1,DNS:localhost
authorityKeyIdentifier = keyid
"""


def tls_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "Manifest" / "bridge-tls"


def _openssl(*args: str, cwd: Path) -> None:
    subprocess.run(["openssl", *args], cwd=cwd, check=True, capture_output=True)


def make_certificate(folder: Path | None = None) -> Path:
    """Create the constrained CA and the bridge's certificate; delete the CA's key."""
    folder = folder or tls_dir()
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "ca.cnf").write_text(_CA_CONFIG)
        (work / "leaf.ext").write_text(_LEAF_EXT)
        _openssl(
            "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key",
            "-out", "ca.pem", "-days", str(DAYS), "-config", "ca.cnf", "-sha256",
            cwd=work,
        )  # fmt: skip
        _openssl(
            "req", "-newkey", "rsa:2048", "-nodes", "-keyout", "bridge.key",
            "-out", "bridge.csr", "-subj", "/CN=127.0.0.1/O=Manifest", "-sha256",
            cwd=work,
        )  # fmt: skip
        _openssl(
            "x509", "-req", "-in", "bridge.csr", "-CA", "ca.pem", "-CAkey", "ca.key",
            "-CAcreateserial", "-out", "bridge.pem", "-days", str(DAYS), "-sha256",
            "-extfile", "leaf.ext",
            cwd=work,
        )  # fmt: skip
        # The CA's key is never kept: it has signed the one certificate it ever will.
        (work / "ca.key").unlink()
        for name in ("ca.pem", "bridge.pem", "bridge.key"):
            shutil.copyfile(work / name, folder / name)
            os.chmod(folder / name, 0o600)
    return folder


def certificate_ok(folder: Path | None = None) -> bool:
    """The bridge certificate exists and isn't about to expire."""
    folder = folder or tls_dir()
    cert = folder / "bridge.pem"
    if not (cert.exists() and (folder / "bridge.key").exists()):
        return False
    checked = subprocess.run(
        ["openssl", "x509", "-checkend", str(RENEW_BEFORE_SECONDS), "-noout", "-in", str(cert)],
        capture_output=True,
    )
    return checked.returncode == 0


def trust(folder: Path | None = None) -> bool:
    """Ask macOS to trust the CA for TLS in the login keychain (password or Touch ID once)."""
    folder = folder or tls_dir()
    keychain = Path.home() / "Library" / "Keychains" / "login.keychain-db"
    done = subprocess.run(
        [
            "security", "add-trusted-cert", "-r", "trustRoot", "-p", "ssl",
            "-k", str(keychain), str(folder / "ca.pem"),
        ],
        capture_output=True,
    )  # fmt: skip
    return done.returncode == 0


def ensure(*, ask_to_trust: bool) -> bool:
    """A usable certificate, made (and trusted, when asked) if needed. True if HTTPS can run."""
    if certificate_ok():
        return True
    if not ask_to_trust:
        return False  # only `--install`, in front of the person, makes and trusts one
    if not shutil.which("openssl") or not shutil.which("security"):
        return False
    make_certificate()
    trusted = trust()
    (tls_dir() / "trusted").write_text(str(int(time.time())) if trusted else "")
    return trusted


def server_context(folder: Path | None = None) -> ssl.SSLContext | None:
    folder = folder or tls_dir()
    if not certificate_ok(folder):
        return None
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(folder / "bridge.pem", folder / "bridge.key")
    return context
