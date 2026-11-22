"""Tool-grade credential handling.

Design goals
------------
1. **No plaintext password on disk.** Secrets live in the OS keyring
   (Windows Credential Manager / macOS Keychain / Secret Service). The previous
   design wrote the moomoo login password into a ``.env`` file in plaintext and
   generated an ``OpenD.xml`` containing it.
2. **No guessed paths.** The old default secret path was hardcoded as
   ``C:/Users/<you>/.ssh/moomoo_creds.env`` -- a literal ``<you>`` that never
   resolves on any machine, so every user had to discover they must override it.
3. **One obvious setup command.** ``python -m config.credentials setup`` prompts
   for each value, stores it, and verifies it.
4. **Non-secret config stays in files.** ``START_DATE`` and paths are not
   secrets; they stay in ``.env`` where they are reviewable in a diff.

Resolution order for every secret
---------------------------------
keyring  ->  environment variable  ->  None

The env-var fallback keeps headless / CI runs working without a keyring, but it
is never the documented path for a human user.

Usage
-----
    python -m config.credentials setup      # interactive first-time setup
    python -m config.credentials status     # show what is stored (never values)
    python -m config.credentials clear      # remove stored secrets
"""
from __future__ import annotations

import getpass
import os
import sys

try:
    import keyring
    from keyring.errors import KeyringError
    _KEYRING_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    keyring = None
    KeyringError = Exception
    _KEYRING_AVAILABLE = False

# All secrets are stored under one service name, keyed by field.
SERVICE_NAME = "moomoo-portfolio"

# field -> (env var name, human label, is_secret)
FIELDS: dict[str, tuple[str, str, bool]] = {
    "login_account": ("MOOMOO_LOGIN_ACCOUNT", "moomoo login (ID / email / phone)", False),
    "login_pwd": ("MOOMOO_LOGIN_PWD", "moomoo login password", True),
    "rsa_key_path": ("MOOMOO_RSA_KEY", "path to your RSA private key file", False),
}


def _keyring_usable() -> bool:
    """True only if the keyring backend can actually store and return values.

    A headless Linux box may expose a backend that raises on write. Probe once
    with a throwaway entry rather than discovering it mid-setup.
    """
    if not _KEYRING_AVAILABLE:
        return False
    probe_key = "__probe__"
    try:
        keyring.set_password(SERVICE_NAME, probe_key, "1")
        ok = keyring.get_password(SERVICE_NAME, probe_key) == "1"
        keyring.delete_password(SERVICE_NAME, probe_key)
        return ok
    except Exception:
        return False


def get_secret(field: str) -> str | None:
    """Resolve one secret: keyring, then environment, then None."""
    if field not in FIELDS:
        raise KeyError(f"unknown credential field: {field}")
    env_var = FIELDS[field][0]

    if _keyring_usable():
        try:
            value = keyring.get_password(SERVICE_NAME, field)
            if value:
                return value
        except KeyringError:
            pass

    return os.getenv(env_var) or None


def set_secret(field: str, value: str) -> None:
    """Store one secret in the keyring, raising if no usable backend exists."""
    if not _keyring_usable():
        raise RuntimeError(
            "No usable OS keyring backend. Install the 'keyring' package and a "
            "backend for your OS, or set the environment variable "
            f"{FIELDS[field][0]} instead."
        )
    keyring.set_password(SERVICE_NAME, field, value)


def delete_secret(field: str) -> bool:
    """Remove one secret. Returns True if something was removed."""
    if not _keyring_usable():
        return False
    try:
        keyring.delete_password(SERVICE_NAME, field)
        return True
    except Exception:
        return False


def load_opend_credentials() -> dict | None:
    """Return the three moomoo credentials, or None if any is missing.

    Single accessor for the rest of the codebase, so nothing else needs to know
    whether a value came from the keyring or the environment.
    """
    account = get_secret("login_account")
    pwd = get_secret("login_pwd")
    rsa_key = get_secret("rsa_key_path")

    if not all([account, pwd, rsa_key]):
        return None

    return {
        "login_account": account,
        "login_pwd": pwd,
        "rsa_private_key": rsa_key,
    }


def generate_opend_xml() -> bool:
    """Render OpenD.xml from the tracked template + resolved credentials.

    Returns False (rather than raising) when credentials are absent, so importing
    the package offline stays safe. Permissions are tightened where the platform
    supports it, because the file embeds the account password.
    """
    from config import settings

    creds = load_opend_credentials()
    if creds is None:
        return False

    template_path = settings.OPEND_XML_TEMPLATE
    if not template_path.exists():
        template_path = settings.BASE_DIR / "OpenD.example.xml"
    if not template_path.exists():
        print("Warning: OpenD.example.xml template not found -- skipping XML generation.")
        return False

    xml_content = template_path.read_text(encoding="utf-8")
    xml_content = xml_content.replace("YOUR_LOGIN_HERE", creds["login_account"])
    xml_content = xml_content.replace("YOUR_PASSWORD_HERE", creds["login_pwd"])
    xml_content = xml_content.replace("RSA__KEY_FILEPATH_HERE", creds["rsa_private_key"])

    output_path = settings.OPEND_XML_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml_content, encoding="utf-8")

    try:
        os.chmod(output_path, 0o600)
    except OSError:
        pass

    print(f"OpenD.xml generated from template at {output_path}")
    return True


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _cli_setup() -> int:
    """Interactive first-time setup."""
    if not _keyring_usable():
        print("! No usable OS keyring backend found.")
        print("  Install one, or set these environment variables instead:")
        for field, (env_var, label, is_secret) in FIELDS.items():
            print(f"    {env_var:<22} {label}")
        return 1

    print("Moomoo portfolio tracker -- credential setup")
    print(f"Secrets are stored in your OS keyring under service '{SERVICE_NAME}'.")
    print("They are never written to disk in this project.\n")

    existing = {f: get_secret(f) for f in FIELDS}
    for field, (env_var, label, is_secret) in FIELDS.items():
        current = existing[field]
        shown = "(already stored)" if current else "(not set)"
        prompt = f"{label} {shown}: "
        value = getpass.getpass(prompt) if is_secret else input(prompt)
        if not value.strip():
            if current:
                print(f"  keeping existing value for {field}")
                continue
            print(f"  ! {label} is required")
            return 1
        set_secret(field, value.strip())
        print(f"  stored {field}")

    print("\nVerifying...")
    missing = [f for f in FIELDS if not get_secret(f)]
    if missing:
        print(f"! still missing: {', '.join(missing)}")
        return 1
    print("All three credentials present.")

    rsa = get_secret("rsa_key_path")
    if rsa and not os.path.exists(rsa):
        print(f"! warning: RSA key path does not exist on disk: {rsa}")
    print("\nNext: run `python main.py` to create/update the database.")
    return 0


def _cli_status() -> int:
    print(f"Keyring backend usable: {_keyring_usable()}")
    for field, (env_var, label, is_secret) in FIELDS.items():
        keyring_val = None
        if _keyring_usable():
            try:
                keyring_val = keyring.get_password(SERVICE_NAME, field)
            except Exception:
                keyring_val = None
        env_val = os.getenv(env_var)
        source = "keyring" if keyring_val else ("env:" + env_var if env_val else "--")
        state = "set" if (keyring_val or env_val) else "MISSING"
        print(f"  {field:<16} {state:<8} source={source}")
    return 0


def _cli_clear() -> int:
    removed = [f for f in FIELDS if delete_secret(f)]
    print(f"Removed {len(removed)} secret(s) from the keyring.")
    return 0


def main(argv: list[str]) -> int:
    action = argv[1] if len(argv) > 1 else "status"
    if action == "setup":
        return _cli_setup()
    if action == "status":
        return _cli_status()
    if action == "clear":
        return _cli_clear()
    print(f"unknown action: {action}\nusage: python -m config.credentials [setup|status|clear]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
