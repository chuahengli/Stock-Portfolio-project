"""
Credential loader for moomoo OpenD.

Loads sensitive credentials from a .env file stored outside the Docker
sandbox (C:\\Users\\hengl\\.ssh\\moomoo_creds.env) and generates the
real OpenD.xml from a template at runtime.

Inside the Docker container (Hermes agent), this path doesn't exist,
so credentials remain invisible to the agent.
"""

import os
from pathlib import Path
from config import settings


def load_opend_credentials() -> dict | None:
    """Load moomoo OpenD credentials from environment variables.

    These are set by the secure .env at C:\\Users\\hengl\\.ssh\\moomoo_creds.env
    which settings.py loads at import time. Returns None if not available.
    """
    account = os.getenv("MOOMOO_LOGIN_ACCOUNT")
    pwd = os.getenv("MOOMOO_LOGIN_PWD")
    rsa_key = os.getenv("MOOMOO_RSA_KEY")

    if not all([account, pwd, rsa_key]):
        return None

    return {
        "login_account": account,
        "login_pwd": pwd,
        "rsa_private_key": rsa_key,
    }


def generate_opend_xml() -> bool:
    """Generate a real OpenD.xml from the example template + credentials.

    Reads the example template, substitutes placeholder values with
    credentials from the secure .env, and writes the result to OpenD.xml
    in the OpenD directory.

    Returns True if the XML was generated, False if no credentials available
    (safe to call inside Docker — no-op outcome).
    """
    creds = load_opend_credentials()
    if creds is None:
        return False

    template_path: Path = settings.OPEND_XML_TEMPLATE
    if not template_path.exists():
        # Fallback 1: try the project root
        template_path = settings.BASE_DIR / "OpenD.example.xml"
    if not template_path.exists():
        # Fallback 2: old location inside the moomoo folder
        template_path = (
            settings.BASE_DIR
            / "moomoo_OpenD_9.6.5618_Windows"
            / "OpenD.example.xml"
        )
    if not template_path.exists():
        print("Warning: OpenD.example.xml template not found — skipping XML generation.")
        return False

    with open(template_path, "r", encoding="utf-8") as f:
        xml_content = f.read()

    # Replace template placeholders with real credentials
    xml_content = xml_content.replace("YOUR_LOGIN_HERE", creds["login_account"])
    xml_content = xml_content.replace("YOUR_PASSWORD_HERE", creds["login_pwd"])
    xml_content = xml_content.replace("RSA__KEY_FILEPATH_HERE", creds["rsa_private_key"])

    output_path: Path = settings.OPEND_XML_PATH
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml_content)

    print(f"OpenD.xml generated from template at {output_path}")
    return True