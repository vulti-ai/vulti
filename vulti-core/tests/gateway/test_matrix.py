"""Tests for Matrix platform adapter and Continuwuity integration."""
import json
import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from gateway.config import Platform, PlatformConfig


# ---------------------------------------------------------------------------
# Platform & Config
# ---------------------------------------------------------------------------

class TestMatrixPlatformEnum:
    def test_matrix_enum_exists(self):
        assert Platform.MATRIX.value == "matrix"

    def test_matrix_in_platform_list(self):
        platforms = [p.value for p in Platform]
        assert "matrix" in platforms


class TestMatrixConfigLoading:
    def test_matrix_enabled_by_default(self, monkeypatch):
        """Matrix should be enabled by default without any env vars."""
        from gateway.config import GatewayConfig, _apply_env_overrides
        config = GatewayConfig()
        _apply_env_overrides(config)

        assert Platform.MATRIX in config.platforms
        mc = config.platforms[Platform.MATRIX]
        assert mc.enabled is True
        assert mc.extra["homeserver_url"] == "http://127.0.0.1:6167"
        assert mc.extra["server_name"] == "localhost"

    def test_matrix_custom_server_name(self, monkeypatch):
        monkeypatch.setenv("MATRIX_SERVER_NAME", "test.local")
        monkeypatch.setenv("MATRIX_HOMESERVER_URL", "http://localhost:6167")

        from gateway.config import GatewayConfig, _apply_env_overrides
        config = GatewayConfig()
        _apply_env_overrides(config)

        mc = config.platforms[Platform.MATRIX]
        assert mc.extra["server_name"] == "test.local"
        assert mc.extra["homeserver_url"] == "http://localhost:6167"

    def test_matrix_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("MATRIX_DISABLED", "true")

        from gateway.config import GatewayConfig, _apply_env_overrides
        config = GatewayConfig()
        _apply_env_overrides(config)

        assert Platform.MATRIX not in config.platforms

    def test_connected_platforms_includes_matrix(self):
        from gateway.config import GatewayConfig, _apply_env_overrides
        config = GatewayConfig()
        _apply_env_overrides(config)

        connected = config.get_connected_platforms()
        assert Platform.MATRIX in connected

    def test_matrix_home_channel_from_env(self, monkeypatch):
        monkeypatch.setenv("MATRIX_HOME_CHANNEL", "!abc123:test.local")
        monkeypatch.setenv("MATRIX_HOME_CHANNEL_NAME", "Hub")

        from gateway.config import GatewayConfig, _apply_env_overrides
        config = GatewayConfig()
        _apply_env_overrides(config)

        mc = config.platforms[Platform.MATRIX]
        assert mc.home_channel is not None
        assert mc.home_channel.chat_id == "!abc123:test.local"
        assert mc.home_channel.name == "Hub"


# ---------------------------------------------------------------------------
# Adapter Init
# ---------------------------------------------------------------------------

class TestMatrixAdapterInit:
    def _make_config(self, **extra):
        config = PlatformConfig()
        config.enabled = True
        config.extra = {
            "homeserver_url": "http://localhost:6167",
            "user_id": "@vulti-default:test.local",
            "password": "testpass",
            "server_name": "test.local",
            **extra,
        }
        return config

    def test_init_parses_config(self):
        from gateway.platforms.matrix import MatrixAdapter
        adapter = MatrixAdapter(self._make_config())

        assert adapter.homeserver_url == "http://localhost:6167"
        assert adapter.user_id == "@vulti-default:test.local"
        assert adapter.password == "testpass"
        assert adapter.server_name == "test.local"
        assert adapter.platform == Platform.MATRIX

    def test_init_with_access_token(self):
        from gateway.platforms.matrix import MatrixAdapter
        adapter = MatrixAdapter(self._make_config(
            access_token="syt_test_token",
            password="",
        ))

        assert adapter.access_token == "syt_test_token"
        assert not adapter.password


# ---------------------------------------------------------------------------
# Requirements Check
# ---------------------------------------------------------------------------

class TestMatrixRequirements:
    def test_check_matrix_requirements(self):
        from gateway.platforms.matrix import check_matrix_requirements
        # matrix-nio should be installed in test env
        assert check_matrix_requirements() is True


# ---------------------------------------------------------------------------
# Authorization Maps
# ---------------------------------------------------------------------------

class TestMatrixAuthorization:
    def test_matrix_in_platform_env_map(self):
        """Matrix should be in the authorization maps in run.py."""
        # We can't easily instantiate GatewayRunner, but we can grep
        # the source to verify the maps include Matrix.
        import inspect
        from gateway.run import GatewayRunner
        source = inspect.getsource(GatewayRunner._is_user_authorized)
        assert "MATRIX_ALLOWED_USERS" in source
        assert "MATRIX_ALLOW_ALL_USERS" in source


# ---------------------------------------------------------------------------
# Send Message Tool
# ---------------------------------------------------------------------------

class TestMatrixSendMessageTool:
    def test_matrix_in_platform_map(self):
        """Matrix should be in the send_message_tool platform map."""
        import inspect
        from tools import send_message_tool as smt_module
        source = inspect.getsource(smt_module)
        assert '"matrix": Platform.MATRIX' in source


# ---------------------------------------------------------------------------
# Cron Delivery
# ---------------------------------------------------------------------------

class TestMatrixCronDelivery:
    def test_matrix_in_cron_platform_map(self):
        """Matrix should be in the cron scheduler platform map."""
        import inspect
        from cron.scheduler import _deliver_result
        source = inspect.getsource(_deliver_result)
        assert '"matrix"' in source


# ---------------------------------------------------------------------------
# Toolset
# ---------------------------------------------------------------------------

class TestMatrixToolset:
    def test_matrix_toolset_exists(self):
        from toolsets import TOOLSETS
        assert "vulti-matrix" in TOOLSETS

    def test_matrix_in_gateway_toolset(self):
        from toolsets import TOOLSETS
        assert "vulti-matrix" in TOOLSETS["vulti-gateway"]["includes"]


# ---------------------------------------------------------------------------
# Continuwuity Config
# ---------------------------------------------------------------------------

class TestContinuwuityConfig:
    def test_generate_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr("gateway.continuwuity.get_vulti_home", lambda: tmp_path)

        from gateway.continuwuity import generate_config
        config_path = generate_config(
            server_name="test.local",
            port=6167,
            data_dir=tmp_path / "data",
        )

        assert config_path.exists()
        content = config_path.read_text()
        assert 'server_name = "test.local"' in content
        assert "port = 6167" in content
        assert "allow_federation = true" in content

    def test_registration_token_persistence(self, tmp_path, monkeypatch):
        monkeypatch.setattr("gateway.continuwuity.get_vulti_home", lambda: tmp_path)

        from gateway.continuwuity import _get_or_create_registration_token
        token1 = _get_or_create_registration_token()
        token2 = _get_or_create_registration_token()
        assert token1 == token2
        assert len(token1) > 20


# ---------------------------------------------------------------------------
# Platform Hints
# ---------------------------------------------------------------------------

class TestMatrixPlatformHints:
    def test_matrix_hint_exists(self):
        from agent.prompt_builder import PLATFORM_HINTS
        assert "matrix" in PLATFORM_HINTS
        assert "Matrix" in PLATFORM_HINTS["matrix"]
