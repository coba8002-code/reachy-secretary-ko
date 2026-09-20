#!/bin/bash
# 관리자 화면을 로봇에서 잠깐 띄운다. 키 입력이 끝나면 내리는 것을 권한다.
clear
cat <<'BANNER'
────────────────────────────────────────────────
  관리자 화면 켜기
────────────────────────────────────────────────

  로봇에서 관리자 화면을 띄웁니다.
  브라우저로 http://192.168.45.147:8765 에 접속해
  Claude API 키를 입력하세요.

  키는 로봇의 0600 파일에 저장되고,
  화면에는 항상 가려서 표시됩니다.

  비밀번호:  root

BANNER
read -p "켜려면 엔터 (끄려면 Ctrl-C) ..."
echo

ROBOT=pollen@192.168.45.147
OPTS="-o ConnectTimeout=15 -o ConnectionAttempts=5 -o StrictHostKeyChecking=accept-new"

ssh -t $OPTS "$ROBOT" '
pkill -f "admin/server.py" 2>/dev/null
cd /home/pollen/secretary
REACHY_ADMIN_HOST=0.0.0.0 nohup ./.venv/bin/python admin/server.py > /tmp/admin.log 2>&1 &
sleep 3
curl -s -m 4 -o /dev/null -w "관리자 화면: HTTP %{http_code}\n" http://localhost:8765/
echo "브라우저에서: http://192.168.45.147:8765"
'

echo
echo "────────────────────────────────────────────────"
echo "  키 입력이 끝나면 아래로 내릴 수 있습니다:"
echo "    ssh pollen@192.168.45.147 'pkill -f admin/server.py'"
echo "────────────────────────────────────────────────"
read -p "엔터로 닫기..."
