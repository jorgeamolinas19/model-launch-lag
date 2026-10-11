#!/usr/bin/env bash
# Questions 2 & 3, end to end, after collect_issues.py has finished.
# Idempotent: every step recomputes from the issues table / raw snapshots.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=${1:-reports}
mkdir -p "$OUT"

echo "== clean (codebook exclusions)";           python3 scripts/clean_issues.py        | tee "$OUT/clean.txt"
echo; echo "== regex baseline labels";            python3 scripts/baseline_regex.py      | tee "$OUT/baseline.txt"
echo; echo "== stratified hand-label sample";     python3 scripts/sample_for_labeling.py | tee "$OUT/sample.txt"
echo; echo "== Q2/Q3 metrics (regex labels)";     python3 scripts/metrics_issues.py --source regex_baseline | tee "$OUT/metrics_regex.txt"
echo; echo "== Q1 support report (for the memo)"; python3 scripts/report_support.py --kind new_arch | tee "$OUT/support_new_arch.txt"
echo
echo "next: python3 scripts/classify_llm.py --model qwen3:4b --split dev --no-think   (CPU, ~25s/issue)"
echo "      fill labels/sample_v2_worksheet.csv, then scripts/eval_classifier.py --import ..."
