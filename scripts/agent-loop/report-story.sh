#!/usr/bin/env bash
# Machine-readable JSON report generator
#
# WP-AL-1C6: extended to compute final_status for the orchestrated
# review/repair/reverify flow while preserving the pre-WP-AL-1C6 behavior
# for flows without review/repair artifacts (AC-46).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

RUN_DIR="${1:-${RUN_DIR:-}}"

if [[ -z "$RUN_DIR" || ! -d "$RUN_DIR" ]]; then
  echo "Usage: $0 <run_directory>" >&2
  echo "Example: $0 $ARTIFACTS_DIR/US-002_20260801_120000" >&2
  exit 1
fi

REPORT_FILE="$RUN_DIR/reports/final-report.json"

# Aggregate all results into final report
"$PYTHON_BIN" - "$RUN_DIR" "$REPORT_FILE" "$HARNESS_PY" <<'PYEOF'
import json
import sys
from pathlib import Path
from datetime import datetime

run_dir = sys.argv[1]
report_file = sys.argv[2]
harness_py = sys.argv[3]
reports_dir = Path(run_dir) / "reports"

# Import harness module for atomic write
sys.path.insert(0, str(Path(harness_py).parent))
from harness import atomic_json_write

# WP-AL-1C6: import the deterministic final-status module from lib/
sys.path.insert(0, str(Path(harness_py).parent.parent / "lib"))
from report_final_status import compute_final_status

report = {
    "metadata": {
        "run_directory": run_dir,
        "generated_at": datetime.now().isoformat(),
        "version": "1.0",
        "passport_included": False
    },
    "verification": None,
    "review": None,
    "repair": None,
    "final_status": "UNKNOWN",
    "passport": None
}

# Load passport if it exists
passport_file = reports_dir / "passport.json"
if passport_file.exists():
    try:
        with open(passport_file) as f:
            report["passport"] = json.load(f)
        report["metadata"]["passport_included"] = True
    except (json.JSONDecodeError, IOError) as e:
        report["passport_error"] = f"Failed to load passport.json: {e}"

# Load verification result (working copy; falls back to initial snapshot so
# direct harness invocations without orchestration keep working)
verify_file = reports_dir / "verify-result.json"
initial_snapshot = reports_dir / "verify-result.initial.json"
reverify_snapshot = reports_dir / "verify-result.reverify.json"

def _load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        return None

initial_verify = _load_json(verify_file) or _load_json(initial_snapshot)
reverify_verify = _load_json(reverify_snapshot)

if initial_verify is not None:
    report["verification"] = initial_verify
elif verify_file.exists():
    report["error"] = "Failed to load verify-result.json"

if reverify_verify is not None:
    report["reverify"] = reverify_verify

# Load and classify review result (WP-AL-1C3 reporting guard)
from review_result_reporting import classify_review_result

review_file = reports_dir / "review-result.json"
review_path = review_file if review_file.exists() else None
classification = classify_review_result(review_path)

report["review_classification"] = classification.category
if classification.category != "ABSENT":
    report["review"] = {
        "status": classification.status_value,
        "recommended_action": classification.recommended_action,
        "classification": classification.category,
    }
    if classification.detail:
        report["review"]["detail"] = classification.detail

# Raw review result (WP-AL-1C6 matrix needs status/recommended_action even
# when the 1C3 classifier categorizes the artifact)
raw_review = _load_json(review_file)

# Load repair results (if any)
repair_adapter_result = _load_json(Path(run_dir) / "repair" / "repair-adapter-result.json")
repair_dir = Path(run_dir) / "repair"
if repair_dir.exists():
    repairs = []
    for repair_file in sorted(repair_dir.glob("repair-*.json")):
        try:
            with open(repair_file) as f:
                repairs.append(json.load(f))
        except (json.JSONDecodeError, IOError):
            pass
    if repairs:
        report["repair"] = {
            "iterations": len(repairs),
            "details": repairs
        }

# Dirty baseline marker (DEC-C6-04)
dirty_marker = _load_json(reports_dir / "dirty-baseline.json")
if dirty_marker is not None:
    report["dirty_baseline"] = dirty_marker

# WP-AL-1C6: deterministic final_status computation.
# Legacy behavior (no review/repair artifacts, no verify_context) is preserved
# through the WP-AL-1C3 classification mapping inside compute_final_status.
report["final_status"] = compute_final_status(
    initial_verify=initial_verify,
    reverify=reverify_verify,
    review_result=raw_review,
    repair_result=repair_adapter_result,
    dirty_marker=dirty_marker,
    review_category=classification.category,
    review_category_final_status=classification.final_status,
)

# Write output atomically
atomic_json_write(report_file, report)

print(json.dumps(report, indent=2))
PYEOF
report_exit=$?

if [[ $report_exit -ne 0 ]]; then
  echo "ERROR: Failed to generate final report" >&2
  exit 1
fi

echo ""
echo "Final report generated: $REPORT_FILE"
