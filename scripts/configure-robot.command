#!/bin/bash
# 설정만 넣고 끝낸다. 앱은 띄우지 않는다 - 마이크가 없으면 의미가 없고,
# 4GB CM4 에 불필요한 부하를 남기지 않는다.
clear
cat <<'BANNER'
────────────────────────────────────────────────
  로봇 설정 (설정만, 앱은 띄우지 않음)
────────────────────────────────────────────────

  systemd drop-in 으로 환경변수만 얹습니다.
  패키지는 건드리지 않아 앱 업데이트에도 남습니다.

  앱은 시작하지 않습니다. 마이크가 준비된 뒤에
  띄우는 것이 맞습니다.

  비밀번호:  root

BANNER
read -p "진행하려면 엔터 ..."
echo

ssh -tt -o ConnectTimeout=15 -o ConnectionAttempts=5 -o StrictHostKeyChecking=accept-new \
  pollen@192.168.45.147 'bash -s' <<'REMOTE'
echo "=== 1. 환경변수 설정 ==="
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

echo
echo "=== 2. 데몬 재시작 ==="
sudo systemctl daemon-reload
sudo systemctl restart reachy-mini-daemon
sleep 15
echo "  상태: $(systemctl is-active reachy-mini-daemon)"

echo
echo "=== 3. 환경변수가 실제로 붙었는지 ==="
PID=$(systemctl show -p MainPID --value reachy-mini-daemon)
sudo tr '\0' '\n' < /proc/$PID/environ 2>/dev/null | grep -E "REACHY_MINI|REALTIME|AUTOLOAD" | sed 's/^/  /' || echo "  확인 불가"

echo
echo "=== 4. 배포된 파일 확인 ==="
echo "  인격:"; ls /home/pollen/secretary/profiles/secretary_ko/ | sed 's/^/    /'
echo "  툴:";   ls /home/pollen/secretary/external_tools/*.py | xargs -n1 basename | sed 's/^/    /'

echo
echo "=== 5. 여유 확인 ==="
free -h | awk '/Mem:/{print "  RAM: "$3" / "$2}'
df -h / | awk 'NR==2{print "  디스크 여유: "$4}'
uptime | sed 's/^/  /'

echo
echo "=== 완료 — 앱은 띄우지 않았습니다 ==="
exit
REMOTE

echo
echo "────────────────────────────────────────────────"
echo "  결과를 Claude 에 붙여넣어 주세요."
echo "────────────────────────────────────────────────"
read -p "엔터를 누르면 창이 닫힙니다..."
