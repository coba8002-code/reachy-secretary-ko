#!/bin/bash
clear
echo "────────────────────────────────────────────────"
echo "  배포 무결성 확인"
echo "────────────────────────────────────────────────"
echo
echo "  비밀번호:  root"
echo
read -p "진행하려면 엔터 ..."
cd "$(dirname "$0")" || exit 1
ROBOT=pollen@192.168.45.147
OPTS="-o ConnectTimeout=15 -o ConnectionAttempts=5 -o StrictHostKeyChecking=accept-new"
scp $OPTS remote/verify.sh "$ROBOT:/tmp/verify.sh" >/dev/null && echo "전송 완료" || exit 1
echo
ssh -t $OPTS "$ROBOT" "chmod +x /tmp/verify.sh && /tmp/verify.sh"
echo
echo "────────────────────────────────────────────────"
read -p "결과 복사 후 엔터로 닫기..."
