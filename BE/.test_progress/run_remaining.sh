#!/usr/bin/env bash
# Chạy tiếp lượt toàn suite Supabase đã dừng ngày 2026-11-16 (chỉ các test chưa chạy + các test đã fail).
# Chạy từ thư mục BE:  bash .test_progress/run_remaining.sh
# KHÔNG export .env.test (lệnh này phải chạy trên Supabase). Không chạy song song với phiên pytest khác.
set -u
cd "$(dirname "$0")/.."
cat .test_progress/remaining.txt .test_progress/failed.txt > .test_progress/_rerun.txt
LOG=.test_progress/supabase_resume_$(date +%F_%H%M).log
echo "start $(date '+%F %T')" > "$LOG"
PYTHONUNBUFFERED=1 .venv/Scripts/python -m pytest -v -rfE --tb=short -p no:cacheprovider @.test_progress/_rerun.txt >> "$LOG" 2>&1
echo "end $(date '+%F %T')" >> "$LOG"
tail -5 "$LOG"
