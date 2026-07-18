"""Pydantic schemas for the dataset status endpoint.

The endpoint returns the verification status of the Golden Dataset,
including expected and actual checksums for semantic integrity comparison.
"""

from typing import Literal

from pydantic import BaseModel, Field


class DatasetStatusResponse(BaseModel):
    """Dataset integrity verification response.

    Attributes:
        status: Verification status — one of:
            - "valid": all expected collections present, checksum matches
            - "invalid": dataset exists but differs from expected fixture
            - "not_loaded": Golden Dataset business tables are empty
        dataset_version: Version identifier for the fixture schema (GOLDEN_DATASET_V1.0)
        checksum_algorithm: Algorithm used for checksum computation (sha256:v1)
        expected_checksum: Expected semantic checksum for the approved fixture
        actual_checksum: Computed checksum from current database state; null if not_loaded
    """

    status: Literal["valid", "invalid", "not_loaded"] = Field(
        ..., description="Verification status of the Golden Dataset"
    )
    dataset_version: str = Field(
        ..., description="Dataset version identifier (e.g., GOLDEN_DATASET_V1.0)"
    )
    checksum_algorithm: str = Field(
        ..., description="Algorithm used for checksum computation"
    )
    expected_checksum: str = Field(
        ..., description="Expected semantic checksum for the approved fixture"
    )
    actual_checksum: str | None = Field(
        ..., description="Computed checksum from current database state; null if not_loaded"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "valid",
                    "dataset_version": "GOLDEN_DATASET_V1.0",
                    "checksum_algorithm": "sha256:v1",
                    "expected_checksum": "sha256:abc123...",
                    "actual_checksum": "sha256:abc123...",
                },
                {
                    "status": "invalid",
                    "dataset_version": "GOLDEN_DATASET_V1.0",
                    "checksum_algorithm": "sha256:v1",
                    "expected_checksum": "sha256:abc123...",
                    "actual_checksum": "sha256:def456...",
                },
                {
                    "status": "not_loaded",
                    "dataset_version": "GOLDEN_DATASET_V1.0",
                    "checksum_algorithm": "sha256:v1",
                    "expected_checksum": "sha256:abc123...",
                    "actual_checksum": None,
                },
            ]
        }
    }
