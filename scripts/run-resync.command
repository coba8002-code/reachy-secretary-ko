#!/bin/bash
clear
echo "────────────────────────────────────────────────"
echo "  툴 재전송 + import 시험"
echo "────────────────────────────────────────────────"
echo
echo "  external_tools 와 profiles 를 다시 보내고,"
echo "  앱 venv 파이썬으로 실제 import 되는지 확인합니다."
echo
echo "  비밀번호:  root"
echo
read -p "진행하려면 엔터 ..."
cd "$(dirname "$0")/.." || exit 1
ROBOT=pollen@192.168.45.147
OPTS="-o ConnectTimeout=15 -o ConnectionAttempts=5 -o StrictHostKeyChecking=accept-new"

echo
echo "=== 재전송 ==="
rsync -azv --exclude '__pycache__' --exclude '*.pyc' -e "ssh $OPTS" \
  ./external_tools ./profiles "$ROBOT:/home/pollen/secretary/" | tail -12

echo
echo "=== 검증 스크립트 전송 ==="
scp $OPTS scripts/remote/resync-verify.sh "$ROBOT:/tmp/rv.sh" >/dev/null && echo "  완료"

echo
echo "=== 로봇에서 검증 ==="
ssh -t $OPTS "$ROBOT" "chmod +x /tmp/rv.sh && /tmp/rv.sh"

echo
echo "────────────────────────────────────────────────"
read -p "결과 복사 후 엔터로 닫기..."
