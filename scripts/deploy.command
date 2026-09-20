#!/bin/bash
# 비서를 로봇에 올린다. 노트북 없이 로봇 단독으로 돌리기 위한 배포다.
clear
cat <<'BANNER'
────────────────────────────────────────────────
  로봇에 비서 배포
────────────────────────────────────────────────

  올라가는 것:
    profiles/secretary_ko   한국어 비서 인격
    external_tools/         일정, 메일, ask_claude
    assistant/              제공자 추상화 (Claude / OpenAI / Gemini / Grok)
    admin/                  키 입력용 관리자 화면
    jarvis/                 알림

  로봇에서 전부 돌아갑니다. 두뇌는 외부 API 를 씁니다.

  비밀번호:  root

BANNER
read -p "진행하려면 엔터 ..."
echo

cd "$(dirname "$0")/.." || exit 1
ROBOT=pollen@192.168.45.147
DEST=/home/pollen/secretary

echo "=== 1. 코드 전송 ==="
rsync -az --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
  -e "ssh -o ConnectTimeout=15 -o ConnectionAttempts=5 -o StrictHostKeyChecking=accept-new" \
  ./assistant ./admin ./vision ./jarvis ./profiles ./external_tools \
  "$ROBOT:$DEST/" && echo "  전송 완료" || { echo "  전송 실패"; exit 1; }

echo
echo "=== 2. 로봇 환경 구성 ==="
ssh -tt -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new "$ROBOT" 'bash -s' <<'REMOTE'
cd /home/pollen/secretary

echo "  파이썬: $(python3 -V 2>&1)"
echo "  여유 디스크: $(df -h / | awk 'NR==2{print $4}')"
echo "  RAM: $(free -h | awk '/Mem:/{print $2}')"

echo
echo "  certifi 설치 (클라우드 API TLS 용)"
python3 -m venv .venv 2>/dev/null || true
./.venv/bin/pip -q install --upgrade pip certifi 2>&1 | tail -1
echo "  완료"

echo
echo "=== 대화 앱 위치 찾기 ==="
for d in ~/.local/share/reachy_mini_conversation_app \
         /venvs/apps_venv/lib/python3.12/site-packages/reachy_mini_conversation_app; do
  [ -e "$d" ] && echo "  발견: $d"
done
ls -d ~/.local/share/* 2>/dev/null | head -5

echo
echo "=== 앱이 읽는 .env 위치 후보 ==="
find /home/pollen -maxdepth 3 -name ".env" 2>/dev/null | head -5 || echo "  없음"

echo
echo "=== 배포 결과 ==="
ls -la /home/pollen/secretary
exit
REMOTE

echo
echo "────────────────────────────────────────────────"
echo "  위 출력을 Claude 에 붙여넣어 주세요."
echo "  (대화 앱 위치를 보고 설정 파일을 어디에 둘지 정합니다)"
echo "────────────────────────────────────────────────"
read -p "엔터를 누르면 창이 닫힙니다..."
