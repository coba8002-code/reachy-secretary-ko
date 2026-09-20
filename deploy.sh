#!/usr/bin/env bash
# Install the secretary onto the Reachy Mini so it runs without a laptop.
#
#   ./deploy.sh 192.168.45.147
#
# The robot is the whole system: it hears, thinks (via a cloud API), speaks and
# moves. This machine is only used to write the code and push it over.
#
# Nothing is assumed about paths - the script looks around the robot first and
# shows you what it found before writing anything.

set -euo pipefail

ROBOT_IP="${1:-192.168.45.147}"
ROBOT_USER="${ROBOT_USER:-pollen}"
REMOTE_DIR="${REMOTE_DIR:-/home/${ROBOT_USER}/secretary}"
SSH_OPTS=(-o ConnectTimeout=8 -o ConnectionAttempts=3 -o StrictHostKeyChecking=accept-new)

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

say "1. 로봇 연결 확인 — ${ROBOT_USER}@${ROBOT_IP}"
if ! ssh "${SSH_OPTS[@]}" -o BatchMode=yes "${ROBOT_USER}@${ROBOT_IP}" true 2>/dev/null; then
  echo "  비밀번호를 물어볼 수 있습니다. 공개 문서상 기본값은 root 입니다."
  ssh "${SSH_OPTS[@]}" "${ROBOT_USER}@${ROBOT_IP}" true \
    || die "SSH 접속 실패. macOS 시스템 설정 > 개인정보 보호 및 보안 > 로컬 네트워크 에서 권한을 켜고 앱을 재시작했는지 확인하세요."
fi
echo "  연결 확인"

say "2. 로봇 환경 조사"
ssh "${SSH_OPTS[@]}" "${ROBOT_USER}@${ROBOT_IP}" bash -s <<'REMOTE'
  echo "  호스트   : $(hostname)"
  echo "  커널     : $(uname -m)"
  echo "  RAM      : $(free -h 2>/dev/null | awk '/Mem:/{print $2" 중 "$3" 사용"}')"
  echo "  디스크   : $(df -h / | awk 'NR==2{print $4" 여유"}')"
  echo "  파이썬   : $(python3 -V 2>&1)"
  for v in /venvs/apps_venv /venvs/mini_daemon; do
    [ -d "$v" ] && echo "  venv     : $v"
  done
  app=$(ls -d /home/*/.local/share/reachy_mini_conversation_app 2>/dev/null | head -1)
  [ -n "$app" ] && echo "  대화앱데이터: $app"
REMOTE

say "3. 코드 전송 → ${REMOTE_DIR}"
ssh "${SSH_OPTS[@]}" "${ROBOT_USER}@${ROBOT_IP}" "mkdir -p '${REMOTE_DIR}'"
# --delete 는 쓰지 않는다. 로봇에만 있는 설정과 얼굴 데이터를 지우면 안 된다.
# macOS 기본 rsync 는 openrsync 라 --info 를 모른다. -v 로 대체.
rsync -azv \
  -e "ssh ${SSH_OPTS[*]}" \
  --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
  ./assistant ./admin ./vision ./jarvis ./profiles ./external_tools \
  "${ROBOT_USER}@${ROBOT_IP}:${REMOTE_DIR}/"
echo "  전송 완료"

say "4. 의존성 설치"
ssh "${SSH_OPTS[@]}" "${ROBOT_USER}@${ROBOT_IP}" bash -s <<REMOTE
  set -e
  cd "${REMOTE_DIR}"
  python3 -m venv .venv 2>/dev/null || true
  ./.venv/bin/pip -q install --upgrade pip
  # 두뇌와 관리자 화면은 표준 라이브러리만 쓴다. certifi 만 TLS 용으로 필요.
  ./.venv/bin/pip -q install certifi
  echo "  기본 설치 완료"
REMOTE

say "5. 다음 할 일"
cat <<NEXT
  관리자 화면을 로봇에서 띄우세요:

    ssh ${ROBOT_USER}@${ROBOT_IP}
    cd ${REMOTE_DIR}
    REACHY_ADMIN_HOST=0.0.0.0 ./.venv/bin/python admin/server.py

  그다음 이 기기 브라우저에서:

    http://${ROBOT_IP}:8765

  거기서 Claude API 키를 넣고 '연결 확인' 을 누르면 됩니다.
NEXT
