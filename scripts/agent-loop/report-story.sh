#!/usr/bin/env bash
# Machine-readable JSON report generator

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

# Load verification result
verify_file = reports_dir / "verify-result.json"
if verify_file.exists():
    try:
        with open(verify_file) as f:
            report["verification"] = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        report["error"] = f"Failed to load verify-result.json: {e}"

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

# Load repair results (if any)
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

# Determine final status
if report["verification"]:
    verify_status = report["verification"].get("overall_status", "UNKNOWN")
    if verify_status == "PASS":
        # WP-AL-1C3: use classification.final_status (six-way dispatch)
        report["final_status"] = classification.final_status
    else:
        if report.get("repair") and report["repair"]["iterations"] > 0:
            report["final_status"] = "REPAIR_EXHAUSTED"
        else:
            report["final_status"] = "VERIFICATION_FAILED"
elif report.get("error"):
    report["final_status"] = "INFRASTRUCTURE_ERROR"

# Write output atomically
atomic_json_write(report_file, report)

print(json.dumps(report, indent=2))
PYEOF

echo ""
echo "Final report generated: $REPORT_FILE"
