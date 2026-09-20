#!/bin/bash
# 오디오 보드 펌웨어를 2.1.2 → 2.1.4 로 올린다.
clear
cat <<'BANNER'
────────────────────────────────────────────────
  오디오 보드 펌웨어 업데이트   2.1.2 → 2.1.4
────────────────────────────────────────────────

  공식 절차와 로봇에 이미 들어있는 공식 파일을 씁니다.

  펌웨어 쓰기 중에는 절대 전원을 끄지 마세요.
  (보통 10~30초면 끝납니다)

  비밀번호:  root

BANNER
read -p "진행하려면 엔터, 취소하려면 Ctrl-C ..."
echo

FW=/venvs/mini_daemon/lib/python3.12/site-packages/reachy_mini/assets/firmware/reachymini_ua_io16_lin_v2.1.4.bin

ssh -t -o ConnectTimeout=10 -o ConnectionAttempts=5 -o StrictHostKeyChecking=accept-new \
  pollen@192.168.45.147 "
set -e
echo '=== 변경 전 상태 ==='
lsusb | grep -i pollen || true
ls -la '$FW'
echo
echo '=== 펌웨어 쓰기 (공식 update.sh 와 동일한 명령) ==='
sudo dfu-util -R -e -a 1 -D '$FW'
echo
echo '=== 보드 재시작 대기 (15초) ==='
sleep 15
echo
echo '=== 변경 후 USB 인식 ==='
lsusb | grep -i pollen || echo '  아직 안 올라옴 - 조금 더 기다려 보세요'
echo
echo '=== 녹음 재시험 (1초) ==='
arecord -D reachymini_audio_src -f S16_LE -r 16000 -c 2 -d 1 /tmp/mictest2.wav 2>&1 | tail -1
python3 - <<'PY'
import wave, array
try:
    w = wave.open('/tmp/mictest2.wav')
    a = array.array('h'); a.frombytes(w.readframes(w.getnframes()))
    peak = max(abs(x) for x in a)
    print(f'  최대진폭 {peak} / 32767')
    print('  ▶ 여전히 무음' if peak < 50 else '  ▶ 신호 있음 — 마이크 복구!')
except Exception as e:
    print('  읽기 실패:', e)
PY
"

echo
echo "────────────────────────────────────────────────"
echo "  위 결과를 복사해서 Claude 에 붙여넣어 주세요."
echo "────────────────────────────────────────────────"
echo
read -p "엔터를 누르면 창이 닫힙니다..."
