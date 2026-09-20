#!/bin/bash
# 로봇 오디오 상태 조사 — 터미널.app 에서 실행됩니다.
clear
cat <<'BANNER'
────────────────────────────────────────────────
  Reachy Mini 마이크 진단
────────────────────────────────────────────────

  로봇에 접속합니다. 비밀번호를 물으면 입력하세요.

      비밀번호:  root

  (입력해도 화면에 아무것도 표시되지 않는 것이 정상입니다)

BANNER

ssh -o ConnectTimeout=10 -o ConnectionAttempts=5 -o StrictHostKeyChecking=accept-new \
  pollen@192.168.45.147 'bash -s' <<'REMOTE'
echo
echo "=== 1. 오디오 입력 장치 ==="
arecord -l 2>&1 | head -8
echo
echo "=== 2. 오디오 출력 장치 ==="
aplay -l 2>&1 | head -6
echo
echo "=== 3. dfu-util 설치 여부 ==="
which dfu-util || echo "  없음 — 설치 필요"
echo
echo "=== 4. USB 오디오 보드 인식 ==="
lsusb 2>/dev/null | grep -i -E "xmos|respeaker|20b1|2886" || lsusb 2>/dev/null | head -6
echo
echo "=== 5. 펌웨어 파일 위치 ==="
find / -name "reachymini_ua_io16*.bin" 2>/dev/null || echo "  못 찾음"
echo
echo "=== 6. .asoundrc ==="
ls -la ~/.asoundrc 2>&1
echo
echo "=== 7. 실제 1초 녹음해서 진폭 확인 ==="
arecord -D reachymini_audio_src -f S16_LE -r 16000 -c 2 -d 1 /tmp/mictest.wav 2>&1 | tail -2
python3 - <<'PY' 2>/dev/null || echo "  (분석 불가)"
import wave, array
try:
    w = wave.open('/tmp/mictest.wav')
    a = array.array('h'); a.frombytes(w.readframes(w.getnframes()))
    print(f"  샘플 {len(a)}개 | 최대진폭 {max(abs(x) for x in a)} / 32767")
except Exception as e:
    print("  읽기 실패:", e)
PY
echo
echo "=== 조사 끝 ==="
REMOTE

echo
echo "────────────────────────────────────────────────"
echo "  위 내용을 전부 복사해서 Claude 에 붙여넣어 주세요."
echo "────────────────────────────────────────────────"
echo
read -p "엔터를 누르면 창이 닫힙니다..."
