#!/bin/bash
# 로봇에서 실행되는 설정 스크립트.
# 파일로 전송한 뒤 실행하므로 heredoc 이 표준입력을 삼키는 문제가 없다.
set -e

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
cat /etc/systemd/system/reachy-mini-daemon.service.d/secretary.conf | sed 's/^/    /'

echo
echo "=== 2. 데몬 재시작 ==="
sudo systemctl daemon-reload
sudo systemctl restart reachy-mini-daemon
sleep 15
echo "  상태: $(systemctl is-active reachy-mini-daemon)"

echo
echo "=== 3. 환경변수 적용 확인 ==="
PID=$(systemctl show -p MainPID --value reachy-mini-daemon)
if [ -n "$PID" ] && [ "$PID" != "0" ]; then
  sudo tr '\0' '\n' < /proc/$PID/environ | grep -E "REACHY_MINI|REALTIME|AUTOLOAD" | sed 's/^/  /' \
    || echo "  환경변수가 보이지 않습니다"
else
  echo "  데몬 PID 를 얻지 못했습니다"
fi

echo
echo "=== 4. 배포 파일 ==="
echo "  인격:"; ls /home/pollen/secretary/profiles/secretary_ko/ 2>/dev/null | sed 's/^/    /'
echo "  툴:";   ls /home/pollen/secretary/external_tools/*.py 2>/dev/null | xargs -n1 basename | sed 's/^/    /'

echo
echo "=== 5. 여유 ==="
free -h | awk '/Mem:/{print "  RAM: "$3" / "$2}'
df -h / | awk 'NR==2{print "  디스크 여유: "$4}'
uptime | sed 's/^/  /'

echo
echo "=== 완료 (앱은 띄우지 않았습니다) ==="
