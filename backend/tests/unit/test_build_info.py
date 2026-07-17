"""Tests for build information module.

Covers:
- package metadata version resolution
- fallback when package metadata is unavailable
- environment-variable Git SHA precedence
- local Git lookup (mocked subprocess)
- Git executable unavailable
- command timeout
- invalid SHA output
- no repository present
- environment value from Settings
- no subprocess at import time
- typed immutable BuildInfo output
"""

from __future__ import annotations

import subprocess
from importlib.metadata import PackageNotFoundError

import pytest

import app.core.build_info as build_info_mod
from app.core.build_info import (
    BuildInfo,
    _normalize_git_sha,
    _resolve_git_sha,
    get_build_info,
)

# ---------------------------------------------------------------------------
# Tests: _get_version
# ---------------------------------------------------------------------------


class TestGetVersion:
    """Tests for _get_version()."""

    def test_returns_installed_package_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When the package is installed, return its real version."""
        monkeypatch.setattr(build_info_mod, "version", lambda name: "1.2.3")  # noqa: PGH003
        assert build_info_mod._get_version() == "1.2.3"

    def test_returns_fallback_when_not_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When PackageNotFoundError is raised, return the dev fallback."""

        def _raise(name: str) -> str:  # noqa: ARG001
            raise PackageNotFoundError()

        monkeypatch.setattr(build_info_mod, "version", _raise)  # noqa: PGH003
        assert build_info_mod._get_version() == "0.0.0-dev"

    def test_fallback_is_deterministic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Multiple fallback invocations return the same value."""

        def _raise(name: str) -> str:  # noqa: ARG001
            raise PackageNotFoundError()

        monkeypatch.setattr(build_info_mod, "version", _raise)  # noqa: PGH003
        v1 = build_info_mod._get_version()
        v2 = build_info_mod._get_version()
        assert v1 == v2 == "0.0.0-dev"


# ---------------------------------------------------------------------------
# Tests: _normalize_git_sha
# ---------------------------------------------------------------------------


class TestNormalizeGitSha:
    """Tests for _normalize_git_sha()."""

    def test_full_sha_lowercase(self) -> None:
        sha = "abcdef0123456789abcdef0123456789abcdef01"
        assert _normalize_git_sha(sha) == sha

    def test_full_sha_normalized_to_lowercase(self) -> None:
        sha = "ABCDEF0123456789ABCDEF0123456789ABCDEF01"
        assert _normalize_git_sha(sha) == sha.lower()

    def test_short_sha_accepted(self) -> None:
        assert _normalize_git_sha("abc0123") == "abc0123"

    def test_short_sha_seven_chars(self) -> None:
        """7-char minimum is a valid Git abbreviated SHA."""
        assert _normalize_git_sha("1234567") == "1234567"

    def test_strips_whitespace(self) -> None:
        assert _normalize_git_sha("  abc0123  \n") == "abc0123"

    def test_too_short_returns_unknown(self) -> None:
        assert _normalize_git_sha("abc012") == "unknown"

    def test_empty_returns_unknown(self) -> None:
        assert _normalize_git_sha("") == "unknown"

    def test_non_hex_returns_unknown(self) -> None:
        assert _normalize_git_sha("xyz0123") == "unknown"

    def test_too_long_returns_unknown(self) -> None:
        assert _normalize_git_sha("a" * 41) == "unknown"

    def test_40_chars_accepted(self) -> None:
        sha = "a" * 40
        assert _normalize_git_sha(sha) == sha


# ---------------------------------------------------------------------------
# Tests: _resolve_git_sha
# ---------------------------------------------------------------------------


class TestResolveGitSha:
    """Tests for _resolve_git_sha()."""

    def test_env_var_takes_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Explicit env var wins even if git command would succeed."""
        monkeypatch.setenv("FORGEMIND_GIT_SHA", "deadbeef1234567")

        # Ensure subprocess is NOT called
        def _fail(*args: object, **kwargs: object) -> None:
            raise AssertionError("subprocess.run should not be called when env var is set")

        monkeypatch.setattr(subprocess, "run", _fail)  # noqa: PGH003
        assert _resolve_git_sha() == "deadbeef1234567"

    def test_env_var_normalized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Env var SHA is normalized to lowercase hex."""
        monkeypatch.setenv("FORGEMIND_GIT_SHA", "  ABCDEF1234567  ")
        assert _resolve_git_sha() == "abcdef1234567"

    def test_env_var_invalid_returns_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Invalid env var (not hex) returns unknown via normalization."""
        monkeypatch.setenv("FORGEMIND_GIT_SHA", "not-hex-sha!@#")
        assert _resolve_git_sha() == "unknown"

    def test_git_command_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When git CLI succeeds, its output is used and normalized."""
        monkeypatch.delenv("FORGEMIND_GIT_SHA", raising=False)
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/git")  # noqa: PGH003

        completed = subprocess.CompletedProcess(
            args=["/usr/bin/git", "rev-parse", "HEAD"],
            returncode=0,
            stdout="a1b2c3d4e5f60000000000000000000000000000\n",
            stderr="",
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: completed)  # noqa: PGH003

        result = _resolve_git_sha()
        assert result == "a1b2c3d4e5f60000000000000000000000000000"

    def test_git_command_nonzero_returns_unknown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-zero exit code (no repo) yields unknown."""
        monkeypatch.delenv("FORGEMIND_GIT_SHA", raising=False)
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/git")  # noqa: PGH003

        completed = subprocess.CompletedProcess(
            args=["/usr/bin/git", "rev-parse", "HEAD"],
            returncode=128,
            stdout="",
            stderr="fatal: not a git repository",
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: completed)  # noqa: PGH003

        assert _resolve_git_sha() == "unknown"

    def test_git_executable_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """shutil.which returns None (git not installed) yields unknown."""
        monkeypatch.delenv("FORGEMIND_GIT_SHA", raising=False)
        monkeypatch.setattr("app.core.build_info.shutil.which", lambda name: None)  # noqa: PGH003
        assert _resolve_git_sha() == "unknown"

    def test_git_command_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TimeoutExpired yields unknown."""
        monkeypatch.delenv("FORGEMIND_GIT_SHA", raising=False)
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/git")  # noqa: PGH003
        monkeypatch.setattr(subprocess, "run", _raise_timeout)  # noqa: PGH003
        assert _resolve_git_sha() == "unknown"

    def test_git_output_invalid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If git produces non-hex output, normalization returns unknown."""
        monkeypatch.delenv("FORGEMIND_GIT_SHA", raising=False)
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/git")  # noqa: PGH003

        completed = subprocess.CompletedProcess(
            args=["/usr/bin/git", "rev-parse", "HEAD"],
            returncode=0,
            stdout="not-a-valid-sha\n",
            stderr="",
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: completed)  # noqa: PGH003

        assert _resolve_git_sha() == "unknown"

    def test_custom_env_var_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A different environment variable name can be specified."""
        monkeypatch.setenv("MY_CUSTOM_SHA_VAR", "abcdef0123456789")
        result = _resolve_git_sha(env_var="MY_CUSTOM_SHA_VAR")
        assert result == "abcdef0123456789"

    def test_no_subprocess_args_contain_shell_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify the subprocess call uses shell=False (by capturing kwargs)."""
        monkeypatch.delenv("FORGEMIND_GIT_SHA", raising=False)
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/git")  # noqa: PGH003

        captured_kwargs: dict[str, object] = {}

        def _capture(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured_kwargs.update(kwargs)
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", _capture)  # noqa: PGH003
        _resolve_git_sha()

        assert captured_kwargs.get("shell") is False
        assert captured_kwargs.get("timeout") is not None


# ---------------------------------------------------------------------------
# Tests: get_build_info
# ---------------------------------------------------------------------------


class TestGetBuildInfo:
    """Tests for get_build_info() and the BuildInfo dataclass."""

    def test_returns_build_info_instance(self) -> None:
        """get_build_info() returns a BuildInfo instance."""
        result = get_build_info(
            git_sha_override="abcdef0123456789",
            environment_override="development",
        )
        assert isinstance(result, BuildInfo)

    def test_build_info_has_required_fields(self) -> None:
        """BuildInfo has all four required fields."""
        result = get_build_info(
            version_override="1.0.0",
            git_sha_override="abcdef0123456789",
            environment_override="production",
        )
        assert result.application_name == "forgemind-backend"
        assert result.version == "1.0.0"
        assert result.git_sha == "abcdef0123456789"
        assert result.environment == "production"

    def test_build_info_is_immutable(self) -> None:
        """BuildInfo (frozen dataclass) raises on field mutation."""
        result = get_build_info(
            git_sha_override="abcdef0123456789",
            environment_override="development",
        )
        with pytest.raises(AttributeError):
            result.version = "other"  # type: ignore[misc]

    def test_overrides_take_precedence(self) -> None:
        """Explicit overrides replace auto-detected values."""
        result = get_build_info(
            application_name="my-app",
            version_override="9.9.9",
            git_sha_override="1234567",
            environment_override="staging",
        )
        assert result.application_name == "my-app"
        assert result.version == "9.9.9"
        assert result.git_sha == "1234567"
        assert result.environment == "staging"

    def test_default_application_name(self) -> None:
        """Default application_name is 'forgemind-backend'."""
        result = get_build_info(
            git_sha_override="abcdef0123456789",
            environment_override="development",
        )
        assert result.application_name == "forgemind-backend"

    def test_environment_defaults_to_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without override, environment comes from Settings."""
        monkeypatch.setattr("app.config.settings.environment", "production")
        result = get_build_info(
            git_sha_override="abcdef0123456789",
        )
        assert result.environment == "production"

    def test_version_uses_package_metadata_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without version_override, the installed package version is used."""
        monkeypatch.setattr(build_info_mod, "version", lambda name: "2.5.0")  # noqa: PGH003
        result = get_build_info(
            git_sha_override="abcdef0123456789",
            environment_override="development",
        )
        assert result.version == "2.5.0"

    def test_version_fallback_when_package_not_installed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When package metadata is missing, version falls back to 0.0.0-dev."""

        def _raise(name: str) -> str:  # noqa: ARG001
            raise PackageNotFoundError()

        monkeypatch.setattr(build_info_mod, "version", _raise)  # noqa: PGH003
        result = get_build_info(
            git_sha_override="abcdef0123456789",
            environment_override="development",
        )
        assert result.version == "0.0.0-dev"

    def test_stable_output_despite_multiple_calls(self) -> None:
        """Multiple calls with same overrides return equal BuildInfo instances."""
        overrides = {
            "application_name": "test-app",
            "version_override": "3.0.0",
            "git_sha_override": "fedcba987654321",
            "environment_override": "development",
        }
        r1 = get_build_info(**overrides)
        r2 = get_build_info(**overrides)
        assert r1 == r2  # frozen dataclass equality


# ---------------------------------------------------------------------------
# Tests: No subprocess at import time
# ---------------------------------------------------------------------------


class TestModuleImportSafety:
    """Verify that importing build_info.py does not execute subprocesses."""

    def test_no_subprocess_at_import(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Patch subprocess.run and verify it's not called during import."""
        import importlib
        import sys

        call_count = 0
        original_run = subprocess.run

        def _tracking_run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
            nonlocal call_count
            call_count += 1
            return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _tracking_run)  # noqa: PGH003

        # Force reimport of the module
        saved = sys.modules.pop("app.core.build_info", None)
        try:
            importlib.reload(importlib.import_module("app.core.build_info"))
        finally:
            if saved is not None:
                sys.modules["app.core.build_info"] = saved
            monkeypatch.setattr(subprocess, "run", original_run)  # noqa: PGH003

        assert call_count == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raise_file_not_found(
    *args: object,  # noqa: ARG001
    **kwargs: object,  # noqa: ARG001
) -> None:
    raise FileNotFoundError("git not found")


def _raise_timeout(
    *args: object,  # noqa: ARG001
    **kwargs: object,  # noqa: ARG001
) -> None:
    raise subprocess.TimeoutExpired(cmd="git", timeout=2.0)


def _raise_sandbox_error(
    *args: object,  # noqa: ARG001
    **kwargs: object,  # noqa: ARG001
) -> None:
    raise OSError("sandbox blocked")
