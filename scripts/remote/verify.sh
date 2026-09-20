#!/bin/bash
# 배포 무결성 확인. 앱은 띄우지 않는다.
echo "=== 툴 디렉터리 전체 ==="
ls -la /home/pollen/secretary/external_tools/

echo
echo "=== 공용 라이브러리 (_secretary_lib) ==="
ls -la /home/pollen/secretary/external_tools/_secretary_lib/ 2>/dev/null || echo "  없음 - 재전송 필요"

echo
echo "=== 인격 파일 내용 확인 (앞 12줄) ==="
head -12 /home/pollen/secretary/profiles/secretary_ko/profile.md

echo
echo "=== 툴 문법 검사 (앱 venv 파이썬으로) ==="
for f in /home/pollen/secretary/external_tools/*.py; do
  /venvs/apps_venv/bin/python -c "import ast,sys; ast.parse(open('$f').read())" 2>/dev/null \
    && echo "  OK   $(basename $f)" || echo "  실패 $(basename $f)"
done

echo
echo "=== 현재 상태 ==="
echo "  데몬: $(systemctl is-active reachy-mini-daemon)"
free -h | awk '/Mem:/{print "  RAM: "$3" / "$2}'
