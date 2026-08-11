"""Regression test for provider-default isolation.

Ensures that module-level environment mutations in integration tests
do not leak into unit tests that verify default provider configuration.

This test explicitly imports an integration test module that previously
polluted os.environ["EMBEDDING_PROVIDER"] at import time, then verifies
that the default provider assertion still passes.
"""

from __future__ import annotations

import importlib
import os
import sys


def test_integration_import_does_not_pollute_provider_default() -> None:
    """Importing integration test modules must not change the default provider.

    Regression test for the bug where test_rest_arq_ingestion_e2e.py executed
    os.environ.setdefault("EMBEDDING_PROVIDER", "fake") at module scope,
    causing subsequent Settings() instantiations to read "fake" instead of
    the default "openai".
    """
    # Capture the current state of EMBEDDING_PROVIDER
    original_env = os.environ.get("EMBEDDING_PROVIDER")

    try:
        # Import the integration test module (which previously polluted the env)
        if "tests.integration.test_rest_arq_ingestion_e2e" in sys.modules:
            # If already imported, reload it to trigger module-level code
            importlib.reload(sys.modules["tests.integration.test_rest_arq_ingestion_e2e"])
        else:
            # Import it fresh
            import tests.integration.test_rest_arq_ingestion_e2e  # noqa: F401

        # Now instantiate Settings and verify the default is still "openai"
        from app.config import Settings

        settings = Settings()
        assert settings.embedding_provider == "openai", (
            f"Expected default provider to be 'openai', got {settings.embedding_provider!r}. "
            "Integration test module polluted the environment."
        )

    finally:
        # Restore the original environment state
        if original_env is None:
            os.environ.pop("EMBEDDING_PROVIDER", None)
        else:
            os.environ["EMBEDDING_PROVIDER"] = original_env
