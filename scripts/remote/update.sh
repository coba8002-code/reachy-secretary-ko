#!/bin/bash
# 관리자 화면을 최신 코드로 갈아끼우고 다시 띄운다.
set -e
cd /home/pollen/secretary
pkill -f "admin/server.py" 2>/dev/null || true
sleep 1
REACHY_ADMIN_HOST=0.0.0.0 nohup ./.venv/bin/python admin/server.py > /tmp/admin.log 2>&1 &
sleep 4
curl -s -m 4 -o /dev/null -w "관리자 화면: HTTP %{http_code}\n" http://localhost:8765/
echo "설정 파일: $(ls -la ~/.local/share/reachy-secretary/config.json 2>/dev/null | awk '{print $1, $NF}')"
