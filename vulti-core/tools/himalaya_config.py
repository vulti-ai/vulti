"""
Generate per-agent himalaya config.toml from email connections.

When an agent has email-type connections in its allowlist, this module
generates a scoped himalaya config containing only the accounts the
agent is permitted to access.  The generated config path is set via
the HIMALAYA_CONFIG env var by inject_credentials().
"""

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def generate_himalaya_config(agent_id: str) -> Optional[Path]:
    """Generate a himalaya config.toml from an agent's allowed email connections.

    Returns the path to the generated config, or None if the agent has no
    email connections.
    """
    from vulti_cli.config import get_vulti_home
    from vulti_cli.connection_registry import ConnectionRegistry

    home = get_vulti_home()
    registry = ConnectionRegistry(home)

    email_connections = [
        c for c in registry.get_for_agent(agent_id) if c.type == "email"
    ]
    if not email_connections:
        return None

    # Write to per-agent directory (deterministic, overwritten each time)
    config_path = home / "agents" / agent_id / "himalaya.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    sections = []
    for i, conn in enumerate(email_connections):
        creds = conn.credentials
        # Derive account name: "email-icloud" -> "icloud"
        account_name = conn.name.removeprefix("email-").replace("-", "_")

        address = creds.get("EMAIL_ADDRESS", "")
        display_name = creds.get("EMAIL_DISPLAY_NAME", "")
        password = creds.get("EMAIL_PASSWORD", "")

        imap_host = creds.get("EMAIL_IMAP_HOST", "")
        imap_port = creds.get("EMAIL_IMAP_PORT", "993")
        imap_encryption = creds.get("EMAIL_IMAP_ENCRYPTION", "tls")
        imap_login = creds.get("EMAIL_IMAP_LOGIN", address)

        smtp_host = creds.get("EMAIL_SMTP_HOST", "")
        smtp_port = creds.get("EMAIL_SMTP_PORT", "587")
        smtp_encryption = creds.get("EMAIL_SMTP_ENCRYPTION", "start-tls")
        smtp_login = creds.get("EMAIL_SMTP_LOGIN", address)

        default_line = "default = true" if i == 0 else ""

        section = f"""[accounts.{account_name}]
email = "{address}"
display-name = "{display_name}"
{default_line}

backend.type = "imap"
backend.host = "{imap_host}"
backend.port = {imap_port}
backend.encryption.type = "{imap_encryption}"
backend.login = "{imap_login}"
backend.auth.type = "password"
backend.auth.raw = "{password}"

message.send.backend.type = "smtp"
message.send.backend.host = "{smtp_host}"
message.send.backend.port = {smtp_port}
message.send.backend.encryption.type = "{smtp_encryption}"
message.send.backend.login = "{smtp_login}"
message.send.backend.auth.type = "password"
message.send.backend.auth.raw = "{password}"
"""
        sections.append(section.strip())

    config_path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    try:
        os.chmod(config_path, 0o600)
    except OSError:
        pass

    return config_path
