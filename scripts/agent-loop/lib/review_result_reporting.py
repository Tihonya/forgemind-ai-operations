"""
WP-AL-1C3: Review-result reporting guard for final-status aggregation.

Narrow deterministic helper that classifies an optional review-result.json
file into one of six categories for report-story.sh to consume.

Category → final_status mapping:
    ABSENT              → VERIFIED
    PASS                → ACCEPTED
    FAIL                → REVIEW_REJECTED
    ERROR_HUMAN_REVIEW  → HUMAN_REVIEW_REQUIRED
    ERROR_OTHER         → INFRASTRUCTURE_ERROR
    INVALID             → INFRASTRUCTURE_ERROR

CLI contract:
    python3 review_result_reporting.py classify [--path <file>]

    stdout: JSON object with keys:
        category, final_status, status_value, recommended_action, detail
    exit: always 0 (classification is output, not success signal)

Deterministic, stdlib-only, no network/LLM/shell. Reuses validate_review_result()
from review_contract.py. Applies redact_text() from failure_context.py for
diagnostic sanitization. Never mutates or deletes the source artifact.

Diagnostic bounds:
    - detail capped at 1024 bytes after sanitization
    - no absolute filesystem paths, raw malformed JSON, or secrets in detail
    - on INVALID, detail contains short human-readable reason only
"""

import json
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

# Narrow import from failure_context.py (approved public API)
from failure_context import redact_text

# Narrow import from review_contract.py (consumed, not modified)
from review_contract import ReviewContractError, validate_review_result

# ---------------------------------------------------------------------------
# Category constants
# ---------------------------------------------------------------------------
REVIEW_CATEGORY_ABSENT = "ABSENT"
REVIEW_CATEGORY_PASS = "PASS"
REVIEW_CATEGORY_FAIL = "FAIL"
REVIEW_CATEGORY_ERROR_HUMAN_REVIEW = "ERROR_HUMAN_REVIEW"
REVIEW_CATEGORY_ERROR_OTHER = "ERROR_OTHER"
REVIEW_CATEGORY_INVALID = "INVALID"

# Final-status mapping
_CATEGORY_TO_FINAL_STATUS = {
    REVIEW_CATEGORY_ABSENT: "VERIFIED",
    REVIEW_CATEGORY_PASS: "ACCEPTED",
    REVIEW_CATEGORY_FAIL: "REVIEW_REJECTED",
    REVIEW_CATEGORY_ERROR_HUMAN_REVIEW: "HUMAN_REVIEW_REQUIRED",
    REVIEW_CATEGORY_ERROR_OTHER: "INFRASTRUCTURE_ERROR",
    REVIEW_CATEGORY_INVALID: "INFRASTRUCTURE_ERROR",
}

# Diagnostic limits
_MAX_DETAIL_BYTES = 1024
_MAX_READ_BYTES = 1_048_576  # 1 MB hard cap


# ---------------------------------------------------------------------------
# Classification result
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ReviewClassification:
    """Immutable classification result for a review-result artifact."""

    category: str  # one of REVIEW_CATEGORY_* constants
    final_status: str  # mapped final_status value
    status_value: str | None  # raw status field if readable, else None
    recommended_action: str | None  # raw recommended_action if readable, else None
    detail: str  # bounded sanitized detail; empty on success


# ---------------------------------------------------------------------------
# File-state safety helpers
# ---------------------------------------------------------------------------
def _is_safe_regular_file(path: Path) -> bool:
    """Return True if path is a regular file (not symlink, FIFO, device, socket, directory)."""
    try:
        # Use lstat to detect symlinks without following them
        st = path.lstat()
    except OSError:
        return False

    # Reject symlinks
    if stat.S_ISLNK(st.st_mode):
        return False

    # Reject non-regular files (directory, FIFO, socket, block/char device)
    return stat.S_ISREG(st.st_mode)


def _sanitize_detail(raw_detail: str) -> str:
    """Apply redact_text and cap at _MAX_DETAIL_BYTES. Never expose absolute paths."""
    if not raw_detail:
        return ""

    # Apply redaction patterns (secrets, tokens, base64, etc.)
    sanitized, _ = redact_text(raw_detail)

    # Remove any absolute paths that might have leaked in (defense in depth)
    # Simple heuristic: replace /path-like segments with <redacted_path>
    # This is conservative — we don't want to mangle legitimate diagnostics
    sanitized = re.sub(r"(?<!\w)/(?:home|tmp|var|etc|usr|run)/[^\s,;\]}\"]*", "<redacted_path>", sanitized)

    # Cap at byte limit
    encoded = sanitized.encode("utf-8", errors="replace")
    if len(encoded) > _MAX_DETAIL_BYTES:
        sanitized = encoded[:_MAX_DETAIL_BYTES].decode("utf-8", errors="ignore")
        sanitized += "... [truncated]"

    return sanitized


# ---------------------------------------------------------------------------
# Core classification logic
# ---------------------------------------------------------------------------
def classify_review_result(path: Path | None) -> ReviewClassification:
    """Classify an optional review-result file for final-report aggregation.

    - If path is None or the file does not exist: ABSENT → VERIFIED.
    - If the file cannot be read (permissions, wrong type): INVALID → INFRASTRUCTURE_ERROR.
    - If JSON parsing fails: INVALID → INFRASTRUCTURE_ERROR.
    - If validate_review_result() raises: INVALID → INFRASTRUCTURE_ERROR.
    - If status == "PASS": PASS → ACCEPTED.
    - If status == "FAIL": FAIL → REVIEW_REJECTED.
    - If status == "ERROR" and recommended_action == "human_review": ERROR_HUMAN_REVIEW → HUMAN_REVIEW_REQUIRED.
    - If status == "ERROR" with any other action: ERROR_OTHER → INFRASTRUCTURE_ERROR.
    - Otherwise (unknown status, missing/wrong-typed fields): INVALID → INFRASTRUCTURE_ERROR.

    Deterministic: identical input produces identical output on repeated execution.
    Never mutates or deletes the source artifact.
    """
    # ABSENT cases
    if path is None:
        return ReviewClassification(
            category=REVIEW_CATEGORY_ABSENT,
            final_status=_CATEGORY_TO_FINAL_STATUS[REVIEW_CATEGORY_ABSENT],
            status_value=None,
            recommended_action=None,
            detail="",
        )

    # Check existence (file may disappear between check and read — handle gracefully)
    try:
        if not path.exists():
            return ReviewClassification(
                category=REVIEW_CATEGORY_ABSENT,
                final_status=_CATEGORY_TO_FINAL_STATUS[REVIEW_CATEGORY_ABSENT],
                status_value=None,
                recommended_action=None,
                detail="",
            )
    except OSError as e:
        return ReviewClassification(
            category=REVIEW_CATEGORY_INVALID,
            final_status=_CATEGORY_TO_FINAL_STATUS[REVIEW_CATEGORY_INVALID],
            status_value=None,
            recommended_action=None,
            detail=_sanitize_detail(f"file existence check failed: {e}"),
        )

    # File-state safety: reject non-regular files (symlink, FIFO, device, socket, directory)
    if not _is_safe_regular_file(path):
        return ReviewClassification(
            category=REVIEW_CATEGORY_INVALID,
            final_status=_CATEGORY_TO_FINAL_STATUS[REVIEW_CATEGORY_INVALID],
            status_value=None,
            recommended_action=None,
            detail=_sanitize_detail("unreadable file type"),
        )

    # Read the file with size limit
    try:
        file_size = path.stat().st_size
        if file_size > _MAX_READ_BYTES:
            return ReviewClassification(
                category=REVIEW_CATEGORY_INVALID,
                final_status=_CATEGORY_TO_FINAL_STATUS[REVIEW_CATEGORY_INVALID],
                status_value=None,
                recommended_action=None,
                detail=_sanitize_detail(f"file exceeds size limit ({file_size} bytes)"),
            )

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        return ReviewClassification(
            category=REVIEW_CATEGORY_INVALID,
            final_status=_CATEGORY_TO_FINAL_STATUS[REVIEW_CATEGORY_INVALID],
            status_value=None,
            recommended_action=None,
            detail=_sanitize_detail(f"file read failed: {e}"),
        )
    except UnicodeDecodeError as e:
        return ReviewClassification(
            category=REVIEW_CATEGORY_INVALID,
            final_status=_CATEGORY_TO_FINAL_STATUS[REVIEW_CATEGORY_INVALID],
            status_value=None,
            recommended_action=None,
            detail=_sanitize_detail(f"encoding error: {e}"),
        )

    # Parse JSON
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return ReviewClassification(
            category=REVIEW_CATEGORY_INVALID,
            final_status=_CATEGORY_TO_FINAL_STATUS[REVIEW_CATEGORY_INVALID],
            status_value=None,
            recommended_action=None,
            detail=_sanitize_detail(f"JSON parse failed: {e}"),
        )

    # Validate it's a dict (top-level must be object)
    if not isinstance(data, dict):
        return ReviewClassification(
            category=REVIEW_CATEGORY_INVALID,
            final_status=_CATEGORY_TO_FINAL_STATUS[REVIEW_CATEGORY_INVALID],
            status_value=None,
            recommended_action=None,
            detail=_sanitize_detail("JSON is not an object"),
        )

    # Schema validation via validate_review_result()
    try:
        validate_review_result(data)
    except ReviewContractError as e:
        return ReviewClassification(
            category=REVIEW_CATEGORY_INVALID,
            final_status=_CATEGORY_TO_FINAL_STATUS[REVIEW_CATEGORY_INVALID],
            status_value=None,
            recommended_action=None,
            detail=_sanitize_detail(f"schema validation failed: {e}"),
        )

    # Extract status and recommended_action (guaranteed present after validation)
    status_value = data.get("status")
    recommended_action = data.get("recommended_action")

    # Classify by status
    if status_value == "PASS":
        return ReviewClassification(
            category=REVIEW_CATEGORY_PASS,
            final_status=_CATEGORY_TO_FINAL_STATUS[REVIEW_CATEGORY_PASS],
            status_value=status_value,
            recommended_action=recommended_action,
            detail="",
        )

    if status_value == "FAIL":
        return ReviewClassification(
            category=REVIEW_CATEGORY_FAIL,
            final_status=_CATEGORY_TO_FINAL_STATUS[REVIEW_CATEGORY_FAIL],
            status_value=status_value,
            recommended_action=recommended_action,
            detail="",
        )

    if status_value == "ERROR":
        if recommended_action == "human_review":
            return ReviewClassification(
                category=REVIEW_CATEGORY_ERROR_HUMAN_REVIEW,
                final_status=_CATEGORY_TO_FINAL_STATUS[REVIEW_CATEGORY_ERROR_HUMAN_REVIEW],
                status_value=status_value,
                recommended_action=recommended_action,
                detail="",
            )
        else:
            # ERROR with any other/missing recommended_action
            return ReviewClassification(
                category=REVIEW_CATEGORY_ERROR_OTHER,
                final_status=_CATEGORY_TO_FINAL_STATUS[REVIEW_CATEGORY_ERROR_OTHER],
                status_value=status_value,
                recommended_action=recommended_action,
                detail="",
            )

    # Unknown status (should not happen after validate_review_result, but fail closed)
    return ReviewClassification(
        category=REVIEW_CATEGORY_INVALID,
        final_status=_CATEGORY_TO_FINAL_STATUS[REVIEW_CATEGORY_INVALID],
        status_value=status_value,
        recommended_action=recommended_action,
        detail=_sanitize_detail(f"unknown status value: {status_value}"),
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main() -> int:
    """CLI: classify [--path <file>]"""
    if len(sys.argv) < 2 or sys.argv[1] != "classify":
        print("Usage: review_result_reporting.py classify [--path <file>]", file=sys.stderr)
        return 1

    path_arg = None
    if len(sys.argv) >= 4 and sys.argv[2] == "--path":
        path_arg = Path(sys.argv[3])

    classification = classify_review_result(path_arg)

    # Emit JSON to stdout
    output = {
        "category": classification.category,
        "final_status": classification.final_status,
        "status_value": classification.status_value,
        "recommended_action": classification.recommended_action,
        "detail": classification.detail,
    }
    print(json.dumps(output, indent=2))

    # Always exit 0 — classification is output, not success signal
    return 0


if __name__ == "__main__":
    sys.exit(main())
