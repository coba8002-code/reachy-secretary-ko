#!/bin/bash
# 진짜 펌웨어(933,888 바이트)를 내려받아 검증한 뒤 플래시한다.
# 1차 시도가 실패한 이유: 저장소의 .bin 들이 Git LFS 포인터(131바이트)였다.
clear
cat <<'BANNER'
────────────────────────────────────────────────
  오디오 펌웨어 2.1.4 — 2차 시도 (올바른 파일)
────────────────────────────────────────────────

  1차 실패 원인: 로봇에 있던 .bin 은 Git LFS 포인터(131바이트)라
  진짜 펌웨어가 아니었습니다. 0바이트에서 멈춰 아무것도 쓰이지
  않았고, 보드는 무사합니다.

  이번에는 로봇이 직접 GitHub LFS 에서 933,888 바이트 원본을
  내려받고, sha256 을 대조한 뒤에만 씁니다.

  ⚠️  쓰기가 시작되면 전원을 끄지 마세요.

  비밀번호:  root

BANNER
read -p "진행하려면 엔터, 취소하려면 Ctrl-C ..."
echo

ssh -t -o ConnectTimeout=10 -o ConnectionAttempts=5 -o StrictHostKeyChecking=accept-new \
  pollen@192.168.45.147 'bash -s' <<'REMOTE'
set -e
URL="https://media.githubusercontent.com/media/pollen-robotics/reachy_mini/main/src/reachy_mini/assets/firmware/reachymini_ua_io16_lin_v2.1.4.bin"
OUT=/tmp/fw_2.1.4.bin
WANT=803c9174f0ddb8bca9bc7fd5418c2051b720391ea6a0c4f77b36267b368446c7

echo "=== 1. 원본 펌웨어 내려받기 ==="
curl -sSL "$URL" -o "$OUT"
ls -la "$OUT"

echo
echo "=== 2. 무결성 검증 ==="
GOT=$(sha256sum "$OUT" | awk '{print $1}')
SIZE=$(stat -c%s "$OUT")
echo "  크기   : $SIZE  (기대 933888)"
echo "  sha256 : $GOT"
if [ "$GOT" != "$WANT" ] || [ "$SIZE" != "933888" ]; then
  echo "  ▶ 불일치 — 중단합니다. 잘못된 파일을 쓰지 않습니다."
  exit 1
fi
echo "  ▶ 일치 — 진짜 펌웨어 확인"

echo
echo "=== 3. 플래시 (중단하지 마세요) ==="
sudo dfu-util -R -e -a 1 -D "$OUT"

echo
echo "=== 4. 보드 재기동 대기 (20초) ==="
sleep 20
lsusb | grep -i pollen || echo "  아직 USB 재인식 전"

echo
echo "=== 5. 녹음 재시험 ==="
arecord -D reachymini_audio_src -f S16_LE -r 16000 -c 2 -d 2 /tmp/mictest3.wav 2>&1 | tail -1
python3 - <<'PY'
import wave, array
try:
    w = wave.open('/tmp/mictest3.wav')
    a = array.array('h'); a.frombytes(w.readframes(w.getnframes()))
    peak = max(abs(x) for x in a)
    print(f'  최대진폭 {peak} / 32767')
    print('  ▶ 여전히 무음 — 하드웨어 문제로 확정' if peak < 50 else '  ▶ 신호 있음 — 마이크 복구 성공!')
except Exception as e:
    print('  읽기 실패:', e)
PY
REMOTE

echo
echo "────────────────────────────────────────────────"
echo "  결과를 복사해서 Claude 에 붙여넣어 주세요."
echo "────────────────────────────────────────────────"
echo
read -p "엔터를 누르면 창이 닫힙니다..."
