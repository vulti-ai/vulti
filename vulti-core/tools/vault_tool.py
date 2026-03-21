"""
Vault Tool — create, verify, and manage Vultisig FastVaults for agents.

The .vult keyshare file is the ONLY source of truth for vault ownership.
No keyshare = no vault. Vault data is never stored in creditcard.json.

Multi-step flow:
  1. create_vault  → spawns `vultisig create fast --two-step`, returns vault_id
  2. verify_vault  → runs `vultisig verify`, exports keyshare to agent dir
  3. get_vault     → returns vault info from .vult keyshare file
  4. delete_vault  → removes keyshare file
"""

import json
import logging
import os
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _vulti_home() -> Path:
    return Path(os.getenv("VULTI_HOME", Path.home() / ".vulti"))


def _agent_id() -> str:
    return os.getenv("VULTI_AGENT_ID", "")


def _agent_dir() -> Path:
    return _vulti_home() / "agents" / _agent_id()


def _vultisig_bin() -> str:
    return str(_vulti_home() / "vultisig-cli" / "node_modules" / ".bin" / "vultisig")


def _run_vultisig(args: list) -> tuple:
    """Run vultisig CLI and return (success, stdout_text, stderr_text)."""
    bin_path = _vultisig_bin()
    if not Path(bin_path).exists():
        return False, "", f"vultisig CLI not installed at {bin_path}"

    try:
        result = subprocess.run(
            [bin_path] + args,
            capture_output=True, text=True, timeout=60,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out (60s)"
    except Exception as e:
        return False, "", str(e)


def _vault_name_from_store(vault_id: str) -> str:
    """Read vault name from ~/.vultisig/ store."""
    store_path = Path.home() / ".vultisig" / f"vault:{vault_id}.json"
    try:
        if store_path.exists():
            data = json.loads(store_path.read_text())
            return data.get("name", "vault")
    except Exception:
        pass
    return "vault"


def _find_vult_file() -> Path | None:
    """Find the first .vult keyshare file in the agent dir."""
    agent_dir = _agent_dir()
    if not agent_dir.exists():
        return None
    for f in agent_dir.iterdir():
        if f.suffix == ".vult":
            return f
    return None


def vault_tool(args: dict) -> str:
    """Handle vault tool calls."""
    action = args.get("action", "")
    agent_id = _agent_id()

    if not agent_id:
        return json.dumps({"success": False, "error": "No VULTI_AGENT_ID set."})

    if action == "create_vault":
        name = args.get("name", "").strip()
        email = args.get("email", "").strip()
        password = args.get("password", "")

        if not name or not email or not password:
            return json.dumps({"success": False, "error": "name, email, and password are required."})

        ok, stdout, stderr = _run_vultisig([
            "create", "fast",
            "--two-step",
            "--name", name,
            "--email", email,
            "--password", password,
            "-o", "json", "--silent",
        ])

        if not ok:
            try:
                err_data = json.loads(stdout or stderr)
                msg = err_data.get("error", {}).get("message", stderr)
            except Exception:
                msg = stderr or "Vault creation failed"
            return json.dumps({"success": False, "error": msg})

        # Parse vault ID from response
        vault_id = None
        try:
            data = json.loads(stdout)
            vault_id = (
                data.get("vaultId") or data.get("vault_id") or data.get("id")
                or (data.get("data", {}) or {}).get("vaultId")
                or (data.get("data", {}) or {}).get("vault_id")
            )
        except Exception:
            pass

        if not vault_id:
            match = re.search(r"[a-fA-F0-9]{60,}", stdout)
            if match:
                vault_id = match.group(0)

        if not vault_id:
            return json.dumps({"success": False, "error": "Could not extract vault ID from response."})

        return json.dumps({
            "success": True,
            "vault_id": vault_id,
            "email": email,
            "message": (
                f"Vault created. A verification code has been sent to {email}. "
                "Ask the user for the 6-digit code, then call "
                f"vault(action='verify_vault', vault_id='{vault_id}', code='<code>', "
                f"password='<same password>')."
            ),
        })

    if action == "verify_vault":
        vault_id = args.get("vault_id", "").strip()
        code = args.get("code", "").strip()
        password = args.get("password", "")

        if not vault_id or not code:
            return json.dumps({"success": False, "error": "vault_id and code are required."})
        if not password:
            return json.dumps({"success": False, "error": "password is required to export the keyshare."})

        # Step 1: Verify with code
        ok, stdout, stderr = _run_vultisig([
            "verify", vault_id,
            "--code", code,
            "-o", "json", "--silent",
        ])
        if not ok:
            try:
                err_data = json.loads(stdout or stderr)
                msg = err_data.get("error", {}).get("message", stderr)
            except Exception:
                msg = stderr or "Verification failed"
            return json.dumps({"success": False, "error": msg})

        # Step 2: Export keyshare — THIS MUST SUCCEED or the vault is unusable
        vault_name = _vault_name_from_store(vault_id)
        export_path = _agent_dir() / f"{vault_name}.vult"
        _agent_dir().mkdir(parents=True, exist_ok=True)

        ok2, stdout2, stderr2 = _run_vultisig([
            "export",
            "--vault", vault_id,
            "--password", password,
            "--silent",
            "-o", str(export_path),
        ])
        if not ok2:
            return json.dumps({
                "success": False,
                "error": f"Vault verified but keyshare export failed: {stderr2}. "
                         "The vault is NOT usable without the keyshare. "
                         "Try again with the correct password.",
            })

        if not export_path.exists():
            return json.dumps({
                "success": False,
                "error": "Keyshare file was not created. Vault is NOT usable.",
            })

        return json.dumps({
            "success": True,
            "vault_id": vault_id,
            "name": vault_name,
            "message": f"Vault '{vault_name}' verified and keyshare exported. Ready to use.",
        })

    if action == "resend_code":
        vault_id = args.get("vault_id", "").strip()
        email = args.get("email", "").strip()
        password = args.get("password", "")

        if not vault_id or not email or not password:
            return json.dumps({"success": False, "error": "vault_id, email, and password are required."})

        ok, stdout, stderr = _run_vultisig([
            "verify", vault_id,
            "--resend",
            "--email", email,
            "--password", password,
            "--silent",
        ])
        if not ok:
            return json.dumps({"success": False, "error": stderr or "Resend failed"})
        return json.dumps({"success": True, "message": f"Verification code resent to {email}."})

    if action == "get_vault":
        vult_file = _find_vult_file()
        if not vult_file:
            return json.dumps({"success": False, "error": "No vault connected (no keyshare file)."})
        vault_name = vult_file.stem
        # .vult is encrypted — use CLI for metadata
        vault_id = ""
        try:
            ok, stdout, _ = _run_vultisig(["vaults", "-o", "json", "--silent"])
            if ok:
                data = json.loads(stdout)
                for v in data.get("data", {}).get("vaults", []):
                    if v.get("name") == vault_name:
                        vault_id = v.get("id", "")
                        break
        except Exception:
            pass
        return json.dumps({
            "success": True,
            "vault_id": vault_id,
            "name": vault_name,
        })

    if action == "portfolio":
        vult_file = _find_vult_file()
        if not vult_file:
            return json.dumps({"success": False, "error": "No vault connected."})
        vault_name = vult_file.stem
        # Get vault ID, then portfolio
        vault_id = ""
        try:
            ok, stdout, _ = _run_vultisig(["vaults", "-o", "json", "--silent"])
            if ok:
                for v in json.loads(stdout).get("data", {}).get("vaults", []):
                    if v.get("name") == vault_name:
                        vault_id = v.get("id", "")
                        break
        except Exception:
            pass
        if not vault_id:
            return json.dumps({"success": False, "error": "Could not find vault ID."})
        ok, stdout, stderr = _run_vultisig([
            "portfolio", "--vault", vault_id, "-o", "json", "--silent",
        ])
        if not ok:
            return json.dumps({"success": False, "error": stderr or "Portfolio fetch failed"})
        try:
            return stdout
        except Exception:
            return json.dumps({"success": False, "error": "Failed to parse portfolio"})

    if action == "delete_vault":
        agent_dir = _agent_dir()
        deleted = False
        if agent_dir.exists():
            for f in agent_dir.iterdir():
                if f.suffix == ".vult":
                    f.unlink()
                    deleted = True
        if deleted:
            return json.dumps({"success": True, "message": "Vault keyshare deleted."})
        return json.dumps({"success": False, "error": "No vault keyshare found to delete."})

    return json.dumps({
        "success": False,
        "error": f"Unknown action '{action}'. Use: create_vault, verify_vault, resend_code, get_vault, portfolio, delete_vault",
    })


def _check_vault_requirements() -> bool:
    """Available when an agent is running and vultisig CLI is installed."""
    if not os.getenv("VULTI_AGENT_ID"):
        return False
    return Path(_vultisig_bin()).exists()


VAULT_SCHEMA = {
    "name": "vault",
    "description": (
        "Create and manage a Vultisig crypto vault. Actions:\n"
        "- create_vault: Create a new FastVault (requires name, email, password). "
        "A verification code will be emailed.\n"
        "- verify_vault: Complete vault creation with the 6-digit email code "
        "(requires vault_id, code, password).\n"
        "- resend_code: Resend the verification email (requires vault_id, email, password).\n"
        "- get_vault: Get current vault info (only if keyshare exists).\n"
        "- portfolio: Get portfolio value and chain balances.\n"
        "- delete_vault: Remove the vault keyshare from this agent."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create_vault", "verify_vault", "resend_code", "get_vault", "portfolio", "delete_vault"],
                "description": "What to do.",
            },
            "name": {
                "type": "string",
                "description": "Vault name (for create_vault).",
            },
            "email": {
                "type": "string",
                "description": "Email for verification (for create_vault, resend_code).",
            },
            "password": {
                "type": "string",
                "description": "Vault password (for create_vault, verify_vault, resend_code).",
            },
            "vault_id": {
                "type": "string",
                "description": "Vault ID (for verify_vault, resend_code, delete_vault).",
            },
            "code": {
                "type": "string",
                "description": "6-digit verification code from email (for verify_vault).",
            },
        },
        "required": ["action"],
    },
}


# --- Registry ---
from tools.registry import registry

registry.register(
    name="vault",
    toolset="wallet",
    schema=VAULT_SCHEMA,
    handler=lambda args, **kw: vault_tool(args),
    check_fn=_check_vault_requirements,
    emoji="🔐",
)
