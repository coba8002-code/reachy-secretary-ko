#!/bin/bash
# 관리자 화면 서비스가 왜 안 뜨는지 본다.
echo "=== 1. 서비스 상태 ==="
systemctl status reachy-secretary-admin --no-pager -l 2>&1 | head -20

echo
echo "=== 2. 최근 로그 ==="
journalctl -u reachy-secretary-admin -n 30 --no-pager 2>&1 | tail -25

echo
echo "=== 3. 서비스 파일 존재 ==="
ls -la /etc/systemd/system/reachy-secretary-admin.service 2>&1

echo
echo "=== 4. 실행 경로 확인 ==="
ls -la /home/pollen/secretary/.venv/bin/python 2>&1
ls -la /home/pollen/secretary/admin/server.py 2>&1
ls /home/pollen/secretary/assistant/ 2>&1

echo
echo "=== 5. 직접 실행해서 에러 보기 ==="
cd /home/pollen/secretary
timeout 6 ./.venv/bin/python admin/server.py 2>&1 | head -20 || true

echo
echo "=== 6. 포트 리스닝 ==="
ss -tlnp 2>/dev/null | grep 8765 || echo "  8765 리스닝 없음"
