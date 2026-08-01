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
"$PYTHON_BIN" - "$RUN_DIR" "$REPORT_FILE" <<'PYEOF'
import json
import sys
from pathlib import Path
from datetime import datetime

run_dir = sys.argv[1]
report_file = sys.argv[2]
reports_dir = Path(run_dir) / "reports"

report = {
    "metadata": {
        "run_directory": run_dir,
        "generated_at": datetime.now().isoformat(),
        "version": "1.0"
    },
    "verification": None,
    "review": None,
    "repair": None,
    "final_status": "UNKNOWN"
}

# Load verification result
verify_file = reports_dir / "verify-result.json"
if verify_file.exists():
    try:
        with open(verify_file) as f:
            report["verification"] = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        report["error"] = f"Failed to load verify-result.json: {e}"

# Load review result (if exists)
review_file = reports_dir / "review-result.json"
if review_file.exists():
    try:
        with open(review_file) as f:
            report["review"] = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        pass  # Review not critical for Phase 1

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
        if report.get("review") and report["review"].get("status") == "PASS":
            report["final_status"] = "ACCEPTED"
        elif report.get("review") and report["review"].get("status") == "FAIL":
            report["final_status"] = "REVIEW_REJECTED"
        else:
            report["final_status"] = "VERIFIED"
    else:
        if report.get("repair") and report["repair"]["iterations"] > 0:
            report["final_status"] = "REPAIR_EXHAUSTED"
        else:
            report["final_status"] = "VERIFICATION_FAILED"
elif report.get("error"):
    report["final_status"] = "INFRASTRUCTURE_ERROR"

# Write output
with open(report_file, 'w') as f:
    json.dump(report, f, indent=2)

print(json.dumps(report, indent=2))
PYEOF

echo ""
echo "Final report generated: $REPORT_FILE"
