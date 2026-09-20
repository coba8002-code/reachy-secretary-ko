#!/bin/bash
# 대화 앱이 우리 인격과 툴을 읽도록 데몬 환경을 설정한다.
#
# 앱은 데몬이 띄우므로 데몬의 환경을 물려받는다. 패키지를 수정하지 않고
# systemd drop-in 으로 환경변수만 얹으면, 앱 업데이트에도 설정이 살아남는다.
clear
cat <<'BANNER'
────────────────────────────────────────────────
  로봇 설정 — 한국어 비서 인격 적용
────────────────────────────────────────────────

  설정할 환경변수:
    REALTIME_TRANSCRIPTION_LANGUAGE=ko
    REACHY_MINI_CUSTOM_PROFILE=secretary_ko
    REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY=/home/pollen/secretary/profiles
    REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY=/home/pollen/secretary/external_tools
    AUTOLOAD_EXTERNAL_TOOLS=1
    REACHY_MINI_APP_TIMEOUT_MINUTES=0

  패키지는 건드리지 않습니다. systemd drop-in 이라
  앱을 업데이트해도 설정이 남습니다.

  비밀번호:  root

BANNER
read -p "진행하려면 엔터 ..."
echo

ssh -tt -o ConnectTimeout=15 -o ConnectionAttempts=5 -o StrictHostKeyChecking=accept-new \
  pollen@192.168.45.147 'bash -s' <<'REMOTE'
echo "=== 1. systemd drop-in 작성 ==="
sudo mkdir -p /etc/systemd/system/reachy-mini-daemon.service.d
sudo tee /etc/systemd/system/reachy-mini-daemon.service.d/secretary.conf >/dev/null <<'CONF'
# reachy-secretary-ko: 한국어 비서 인격과 툴을 대화 앱에 연결한다.
# 앱은 데몬이 띄우므로 이 환경을 물려받는다.
[Service]
Environment=REALTIME_TRANSCRIPTION_LANGUAGE=ko
Environment=REACHY_MINI_CUSTOM_PROFILE=secretary_ko
Environment=REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY=/home/pollen/secretary/profiles
Environment=REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY=/home/pollen/secretary/external_tools
Environment=AUTOLOAD_EXTERNAL_TOOLS=1
Environment=REACHY_MINI_APP_TIMEOUT_MINUTES=0
CONF
echo "  작성 완료"
cat /etc/systemd/system/reachy-mini-daemon.service.d/secretary.conf

echo
echo "=== 2. 데몬 재시작 ==="
sudo systemctl daemon-reload
sudo systemctl restart reachy-mini-daemon
sleep 12
systemctl is-active reachy-mini-daemon

echo
echo "=== 3. 환경변수가 실제로 붙었는지 ==="
PID=$(systemctl show -p MainPID --value reachy-mini-daemon)
sudo tr '\0' '\n' < /proc/$PID/environ 2>/dev/null | grep -E "REACHY_MINI|REALTIME|AUTOLOAD" || echo "  확인 불가"

echo
echo "=== 4. 프로필 파일 확인 ==="
ls -la /home/pollen/secretary/profiles/secretary_ko/
echo
echo "=== 5. 툴 파일 확인 ==="
ls /home/pollen/secretary/external_tools/

echo
echo "=== 6. 대화 앱 시작 ==="
sleep 3
curl -s -m 60 -X POST http://localhost:8000/api/apps/start-app/reachy_mini_conversation_app | head -c 200
echo
sleep 15
curl -s -m 8 http://localhost:8000/api/apps/current-app-status | head -c 200
echo
exit
REMOTE

echo
echo "────────────────────────────────────────────────"
echo "  결과를 Claude 에 붙여넣어 주세요."
echo "────────────────────────────────────────────────"
read -p "엔터를 누르면 창이 닫힙니다..."
