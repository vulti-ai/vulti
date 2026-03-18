"""
Continuwuity (Matrix homeserver) lifecycle management.

Downloads, configures, and manages a Continuwuity homeserver binary
as a subprocess tied to the gateway lifecycle. Each Vulti Hub instance
runs its own Continuwuity instance, enabling Matrix federation between
agents and humans.
"""

import asyncio
import logging
import os
import platform
import secrets
import signal
import stat
from pathlib import Path
from typing import Optional

from vulti_cli.config import get_vulti_home

logger = logging.getLogger(__name__)

# Default port chosen to avoid common conflicts (8008, 8080, etc.)
DEFAULT_PORT = 6167
STARTUP_TIMEOUT = 20  # seconds to wait for readiness
HEALTH_CHECK_INTERVAL = 30  # seconds between health checks

# GitHub release info for auto-download
CONTINUWUITY_REPO = "continuwuity/continuwuity"


def _continuwuity_dir() -> Path:
    """Return the Continuwuity data directory (~/.vulti/continuwuity/)."""
    d = get_vulti_home() / "continuwuity"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _bin_dir() -> Path:
    """Return the bin directory (~/.vulti/bin/)."""
    d = get_vulti_home() / "bin"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tokens_dir() -> Path:
    """Return the tokens directory for agent Matrix credentials."""
    d = _continuwuity_dir() / "tokens"
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_binary() -> Optional[Path]:
    """Find the Continuwuity binary.

    Checks in order:
    1. Bundled sidecar from Vulti Hub app (written by Tauri on startup)
    2. ~/.vulti/bin/continuwuity (local install or cargo build)
    3. System PATH

    Returns the Path if found, None otherwise.
    """
    import shutil

    # 1. Check for bundled sidecar path (written by Vulti Hub Tauri app)
    sidecar_marker = _continuwuity_dir() / "sidecar_path"
    if sidecar_marker.exists():
        sidecar_path = Path(sidecar_marker.read_text().strip())
        if sidecar_path.exists() and os.access(str(sidecar_path), os.X_OK):
            return sidecar_path

    # 2. Check local install
    local_bin = _bin_dir() / "continuwuity"
    if local_bin.exists() and os.access(str(local_bin), os.X_OK):
        return local_bin

    # 3. Check system PATH
    for name in ("continuwuity", "conduwuit"):
        system_bin = shutil.which(name)
        if system_bin:
            return Path(system_bin)

    return None


async def download_binary() -> Optional[Path]:
    """Download or build the Continuwuity binary for the current platform.

    Tries in order:
    1. Download prebuilt binary from GitHub releases
    2. Build from source using cargo (if Rust is installed)

    Returns the Path on success, None on failure.
    """
    target_path = _bin_dir() / "continuwuity"

    # Try downloading a prebuilt binary first
    downloaded = await _try_download_binary(target_path)
    if downloaded:
        return downloaded

    # Fallback: build from source with cargo
    built = await _try_cargo_install(target_path)
    if built:
        return built

    return None


async def _try_download_binary(target_path: Path) -> Optional[Path]:
    """Try to download a prebuilt binary from GitHub releases."""
    import httpx

    system = platform.system().lower()
    machine = platform.machine().lower()

    # Map platform to possible asset name patterns
    # Continuwuity uses names like: conduwuit-linux-arm64, conduwuit-linux-amd64
    if system == "linux":
        if machine in ("arm64", "aarch64"):
            patterns = ["linux-arm64", "aarch64-unknown-linux"]
        else:
            patterns = ["linux-amd64", "x86_64-unknown-linux"]
    elif system == "darwin":
        if machine in ("arm64", "aarch64"):
            patterns = ["macos-arm64", "aarch64-apple-darwin", "darwin-arm64"]
        else:
            patterns = ["macos-amd64", "x86_64-apple-darwin", "darwin-amd64"]
    else:
        return None

    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            # Search through recent releases (not just latest — some may lack assets)
            resp = await client.get(
                f"https://api.github.com/repos/{CONTINUWUITY_REPO}/releases",
                headers={"Accept": "application/vnd.github.v3+json"},
                params={"per_page": 5},
            )
            resp.raise_for_status()
            releases = resp.json()

            for release in releases:
                assets = release.get("assets", [])
                if not assets:
                    continue

                for asset in assets:
                    name = asset["name"].lower()
                    if name.endswith((".sha256", ".sig", ".txt")):
                        continue
                    if any(p in name for p in patterns):
                        # Prefer non-maxperf for smaller binary
                        if "maxperf" in name:
                            continue
                        download_url = asset["browser_download_url"]
                        logger.info("Continuwuity: downloading %s from %s", asset["name"], release["tag_name"])
                        dl = await client.get(download_url)
                        dl.raise_for_status()
                        target_path.write_bytes(dl.content)
                        target_path.chmod(target_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
                        logger.info("Continuwuity: installed to %s", target_path)
                        return target_path

            logger.info("Continuwuity: no prebuilt binary for %s/%s in recent releases", system, machine)

    except Exception as e:
        logger.warning("Continuwuity: download attempt failed: %s", e)

    return None


async def _try_cargo_install(target_path: Path) -> Optional[Path]:
    """Try to build Continuwuity from source using cargo."""
    import shutil

    cargo = shutil.which("cargo")
    if not cargo:
        logger.info("Continuwuity: cargo not found, cannot build from source")
        return None

    build_dir = _continuwuity_dir() / "source"

    # Clone or update the repo
    if (build_dir / ".git").exists():
        logger.info("Continuwuity: updating source...")
        proc = await asyncio.create_subprocess_exec(
            "git", "pull", "--ff-only",
            cwd=str(build_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
    else:
        logger.info("Continuwuity: cloning source (first time)...")
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth", "1",
            f"https://github.com/{CONTINUWUITY_REPO}.git",
            str(build_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode != 0:
            logger.warning("Continuwuity: git clone failed: %s", stderr.decode(errors="replace")[:300])
            return None

    logger.info("Continuwuity: building from source with cargo (this may take several minutes on first run)...")

    try:
        proc = await asyncio.create_subprocess_exec(
            cargo, "build", "--release",
            cwd=str(build_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)

        if proc.returncode == 0:
            # Find the built binary
            for name in ("continuwuity", "conduwuit", "conduit"):
                built_bin = build_dir / "target" / "release" / name
                if built_bin.exists():
                    import shutil as sh
                    sh.copy2(str(built_bin), str(target_path))
                    target_path.chmod(target_path.stat().st_mode | stat.S_IEXEC)
                    logger.info("Continuwuity: built and installed to %s", target_path)
                    return target_path

            logger.warning("Continuwuity: cargo build succeeded but binary not found in target/release/")
        else:
            logger.warning("Continuwuity: cargo build failed (exit %d): %s",
                           proc.returncode, stderr.decode(errors="replace")[:500])

    except asyncio.TimeoutError:
        logger.warning("Continuwuity: cargo build timed out (10 min limit)")
    except Exception as e:
        logger.warning("Continuwuity: cargo build error: %s", e)

    return None


def _get_or_create_registration_token() -> str:
    """Get or create a persistent registration token for user signup."""
    token_path = _continuwuity_dir() / "registration_token"
    if token_path.exists():
        token = token_path.read_text().strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    token_path.write_text(token)
    try:
        token_path.chmod(0o600)
    except OSError:
        pass
    return token


def generate_config(
    server_name: str,
    port: int = DEFAULT_PORT,
    data_dir: Optional[Path] = None,
) -> Path:
    """Generate a Continuwuity TOML config file.

    Args:
        server_name: The Matrix server name (e.g., 'mymachine.tailnet.ts.net').
        port: Port for the homeserver to listen on.
        data_dir: Database directory. Defaults to ~/.vulti/continuwuity/data.

    Returns:
        Path to the generated config file.
    """
    base_dir = _continuwuity_dir()
    if data_dir is None:
        data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    registration_token = _get_or_create_registration_token()

    config_content = f"""\
[global]
server_name = "{server_name}"
database_path = "{data_dir}"
address = "127.0.0.1"
port = {port}

# Registration — open since access is controlled by Tailscale network
allow_registration = true
yes_i_am_very_very_sure_i_want_an_open_registration_server_prone_to_abuse = true

# Federation
allow_federation = true

# Limits
max_request_size = 20971520

# Logging
log = "warn,continuwuity=info"

[global.well_known]
client = "https://{server_name}"
server = "{server_name}:443"
"""

    config_path = base_dir / "conduit.toml"
    config_path.write_text(config_content)
    logger.info("Continuwuity: config written to %s", config_path)
    return config_path


class ContinuwuityManager:
    """Manages the Continuwuity homeserver subprocess lifecycle."""

    def __init__(
        self,
        server_name: str,
        port: int = DEFAULT_PORT,
        data_dir: Optional[Path] = None,
    ):
        self.server_name = server_name
        self.port = port
        self.data_dir = data_dir
        self._process: Optional[asyncio.subprocess.Process] = None
        self._binary_path: Optional[Path] = None
        self._health_task: Optional[asyncio.Task] = None

    @property
    def homeserver_url(self) -> str:
        """Local URL for the homeserver."""
        return f"http://127.0.0.1:{self.port}"

    @property
    def registration_token(self) -> str:
        """The registration token for creating new users."""
        return _get_or_create_registration_token()

    async def start(self) -> bool:
        """Start the Continuwuity homeserver.

        Downloads the binary if not found, generates config, and spawns
        the process. Waits for the server to be ready.

        Returns True on success, False on failure.
        """
        # Find or download binary
        self._binary_path = find_binary()
        if not self._binary_path:
            logger.info("Continuwuity: binary not found, attempting download...")
            self._binary_path = await download_binary()
            if not self._binary_path:
                logger.error(
                    "Continuwuity: could not find or download binary. "
                    "Install manually: https://github.com/%s", CONTINUWUITY_REPO
                )
                return False

        # Generate config
        config_path = generate_config(
            server_name=self.server_name,
            port=self.port,
            data_dir=self.data_dir,
        )

        # Spawn process — capture stdout to extract bootstrap token on first run
        env = os.environ.copy()
        env["CONDUIT_CONFIG"] = str(config_path)

        try:
            self._process = await asyncio.create_subprocess_exec(
                str(self._binary_path),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            logger.info(
                "Continuwuity: started (PID %d) on port %d",
                self._process.pid, self.port,
            )
        except Exception as e:
            logger.error("Continuwuity: failed to start: %s", e)
            return False

        # Wait for readiness
        ready = await self._wait_for_ready()
        if not ready:
            logger.error("Continuwuity: failed to become ready within %ds", STARTUP_TIMEOUT)
            await self.stop()
            return False

        # On first run, Continuwuity requires the first user to be created
        # with a one-time bootstrap token (printed to stdout). The config
        # registration_token only works after that. We bootstrap automatically.
        await self._bootstrap_first_user()

        # Start health monitor
        self._health_task = asyncio.create_task(self._health_monitor())

        logger.info("Continuwuity: ready at %s", self.homeserver_url)
        return True

    async def _wait_for_ready(self) -> bool:
        """Poll the versions endpoint until the server is ready.

        Also reads stdout to capture the bootstrap token on first run.
        """
        import httpx
        import re

        url = f"{self.homeserver_url}/_matrix/client/versions"
        deadline = asyncio.get_event_loop().time() + STARTUP_TIMEOUT
        self._bootstrap_token = None

        # Start a background task to read stderr for the bootstrap token
        # (Continuwuity prints the welcome message with the token to stderr)
        async def _read_stderr():
            if not self._process or not self._process.stderr:
                return
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    break
                text = line.decode(errors="replace").strip()
                # Strip ANSI escape codes for matching
                clean = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
                # Look for: "using the registration token <TOKEN> ."
                # The token line looks like: "...using the registration token ABC123XYZ . Pick your..."
                # Token is alphanumeric, 16+ chars
                match = re.search(r"registration token\s+([A-Za-z0-9]{8,})", clean)
                if match:
                    self._bootstrap_token = match.group(1).strip()
                    logger.info("Continuwuity: captured bootstrap token (%d chars)", len(self._bootstrap_token))

        stderr_task = asyncio.create_task(_read_stderr())

        while asyncio.get_event_loop().time() < deadline:
            # Check if process died
            if self._process and self._process.returncode is not None:
                stderr = ""
                if self._process.stderr:
                    try:
                        stderr = (await self._process.stderr.read()).decode(errors="replace")
                    except Exception:
                        pass
                logger.error("Continuwuity: process exited with code %d: %s",
                             self._process.returncode, stderr[:500])
                stdout_task.cancel()
                return False

            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        # Give stdout reader a moment to capture the token
                        await asyncio.sleep(0.5)
                        return True
            except Exception:
                pass

            await asyncio.sleep(1.0)

        stderr_task.cancel()
        return False

    async def _bootstrap_first_user(self) -> None:
        """Create the first admin user if this is a fresh homeserver.

        Continuwuity requires the first user to be registered with a
        one-time bootstrap token (printed to stdout on first run).
        After the first user exists, the config registration_token works.
        """
        import httpx

        # Check if the config token already works (= first user exists)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self.homeserver_url}/_matrix/client/v1/register/m.login.registration_token/validity",
                    params={"token": self.registration_token},
                )
                if resp.status_code == 200 and resp.json().get("valid"):
                    return  # Config token works, first user already exists
        except Exception:
            pass

        # Need to bootstrap — use the captured bootstrap token
        if not self._bootstrap_token:
            logger.warning("Continuwuity: no bootstrap token captured, cannot create first user")
            return

        logger.info("Continuwuity: bootstrapping first admin user with token '%s'...", self._bootstrap_token)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                url = f"{self.homeserver_url}/_matrix/client/v3/register"

                # Step 1: get session
                resp = await client.post(url, json={
                    "username": "vulti-admin",
                    "password": secrets.token_urlsafe(32),
                    "inhibit_login": False,
                })

                if resp.status_code == 401:
                    session = resp.json().get("session", "")

                    # Step 2: register with bootstrap token
                    resp2 = await client.post(url, json={
                        "username": "vulti-admin",
                        "password": secrets.token_urlsafe(32),
                        "inhibit_login": False,
                        "auth": {
                            "type": "m.login.registration_token",
                            "token": self._bootstrap_token,
                            "session": session,
                        },
                    })

                    if resp2.status_code == 200:
                        logger.info("Continuwuity: first admin user created, config token now active")
                    else:
                        logger.warning("Continuwuity: bootstrap registration failed: %s", resp2.text[:200])
                elif resp.status_code == 200:
                    logger.info("Continuwuity: first user created (open registration)")

        except Exception as e:
            logger.warning("Continuwuity: bootstrap error: %s", e)

    async def stop(self) -> None:
        """Stop the Continuwuity homeserver."""
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None

        if self._process and self._process.returncode is None:
            logger.info("Continuwuity: stopping (PID %d)...", self._process.pid)
            try:
                self._process.send_signal(signal.SIGTERM)
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("Continuwuity: SIGTERM timeout, sending SIGKILL")
                    self._process.kill()
                    await self._process.wait()
            except ProcessLookupError:
                pass  # Already dead
            logger.info("Continuwuity: stopped")

        self._process = None

    async def ensure_running(self) -> bool:
        """Check if the server is running and restart if needed."""
        if self._process and self._process.returncode is None:
            # Process is alive, check health
            import httpx
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"{self.homeserver_url}/_matrix/client/versions")
                    if resp.status_code == 200:
                        return True
            except Exception:
                pass

        # Not running or unhealthy — restart
        logger.warning("Continuwuity: not running, restarting...")
        await self.stop()
        return await self.start()

    async def _health_monitor(self) -> None:
        """Periodically check server health and restart if needed."""
        while True:
            try:
                await asyncio.sleep(HEALTH_CHECK_INTERVAL)
                await self.ensure_running()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Continuwuity health check error: %s", e)
