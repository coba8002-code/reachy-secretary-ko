#!/bin/bash
# 우리 인격과 툴을 대화 앱이 찾을 수 있는 자리에 넣고, 관리자 화면을 띄운다.
clear
cat <<'BANNER'
────────────────────────────────────────────────
  비서 인격 설치 + 관리자 화면 기동
────────────────────────────────────────────────

  1. 대화 앱이 프로필을 어디서 읽는지 찾습니다
  2. 한국어 비서 인격과 툴을 그 자리에 넣습니다
  3. 관리자 화면을 백그라운드로 띄웁니다

  비밀번호:  root

BANNER
read -p "진행하려면 엔터 ..."
echo

ssh -tt -o ConnectTimeout=15 -o ConnectionAttempts=5 -o StrictHostKeyChecking=accept-new \
  pollen@192.168.45.147 'bash -s' <<'REMOTE'
APP=/venvs/apps_venv/lib/python3.12/site-packages/reachy_mini_conversation_app
SRC=/home/pollen/secretary

echo "=== 1. 앱 내부 구조 ==="
ls -d $APP/../profiles $APP/profiles $APP/tools 2>/dev/null
echo "  --- 패키지 최상위 ---"
ls $APP | head -20

echo
echo "=== 2. 프로필 디렉터리 후보 ==="
for d in $APP/profiles $APP/../profiles /venvs/apps_venv/profiles; do
  [ -d "$d" ] && { echo "  발견: $d"; ls "$d" | head -6; }
done

echo
echo "=== 3. 설정 파일이 어디를 가리키는지 ==="
grep -n "DEFAULT_PROFILES_DIRECTORY\|packaged_profiles\|EXTERNAL_PROFILES" $APP/config.py 2>/dev/null | head -8

echo
echo "=== 4. 앱 실행 환경 (데몬 서비스 설정) ==="
systemctl cat reachy-mini-daemon 2>/dev/null | grep -iE "Environment|WorkingDirectory|ExecStart" | head -8

echo
echo "=== 5. 우리 프로필/툴 설치 ==="
TARGET=""
for d in $APP/profiles $APP/../profiles; do
  [ -d "$d" ] && { TARGET="$d"; break; }
done
if [ -n "$TARGET" ]; then
  sudo cp -r $SRC/profiles/secretary_ko "$TARGET/" && echo "  인격 설치: $TARGET/secretary_ko"
  sudo cp $SRC/external_tools/*.py $APP/tools/ 2>/dev/null && echo "  툴 설치: $APP/tools/"
  sudo cp -r $SRC/external_tools/_secretary_lib $APP/tools/ 2>/dev/null
  ls "$TARGET" | head -20
else
  echo "  프로필 디렉터리를 못 찾았습니다 - 위 출력을 보고 다시 정합니다"
fi

echo
echo "=== 6. 관리자 화면 기동 ==="
pkill -f "admin/server.py" 2>/dev/null
cd $SRC
REACHY_ADMIN_HOST=0.0.0.0 nohup ./.venv/bin/python admin/server.py > /tmp/admin.log 2>&1 &
sleep 3
curl -s -m 4 -o /dev/null -w "  관리자 화면: HTTP %{http_code}\n" http://localhost:8765/
echo "  브라우저에서: http://192.168.45.147:8765"
exit
REMOTE

echo
echo "────────────────────────────────────────────────"
echo "  위 출력을 Claude 에 붙여넣어 주세요."
echo "────────────────────────────────────────────────"
read -p "엔터를 누르면 창이 닫힙니다..."
