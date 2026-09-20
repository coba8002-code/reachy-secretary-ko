#!/bin/bash
# 설정 스크립트를 로봇에 보내고 실행한다.
clear
cat <<'BANNER'
────────────────────────────────────────────────
  로봇 설정
────────────────────────────────────────────────

  스크립트를 로봇에 보낸 뒤 실행합니다.
  비밀번호를 두 번 물어볼 수 있습니다 (전송 / 실행).

  비밀번호:  root

BANNER
read -p "진행하려면 엔터 ..."
echo

cd "$(dirname "$0")" || exit 1
ROBOT=pollen@192.168.45.147
OPTS="-o ConnectTimeout=15 -o ConnectionAttempts=5 -o StrictHostKeyChecking=accept-new"

echo "=== 스크립트 전송 ==="
scp $OPTS remote/configure.sh "$ROBOT:/tmp/configure.sh" && echo "  전송 완료" || { echo "  전송 실패"; read -p "엔터로 종료"; exit 1; }

echo
echo "=== 로봇에서 실행 ==="
ssh -t $OPTS "$ROBOT" "chmod +x /tmp/configure.sh && /tmp/configure.sh"

echo
echo "────────────────────────────────────────────────"
echo "  결과를 Claude 에 붙여넣어 주세요."
echo "────────────────────────────────────────────────"
read -p "엔터를 누르면 창이 닫힙니다..."
