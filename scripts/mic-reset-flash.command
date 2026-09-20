#!/bin/bash
# USB 를 리셋해 보드를 정상 상태로 되돌린 뒤 플래시한다.
# 전원을 끄지 않고 해결되는지 먼저 시도한다.
clear
cat <<'BANNER'
────────────────────────────────────────────────
  USB 리셋 후 펌웨어 2.1.4 플래시
────────────────────────────────────────────────

  2차 실패 원인: 1차 중단이 남긴 USB 상태 때문에 보드가
  인터페이스 전환에 응답하지 않았습니다. 파일 자체는
  933,888 바이트 원본으로 검증까지 통과했습니다.

  이번에는 USB 를 소프트웨어로 리셋한 뒤 다시 씁니다.
  (전원을 끄지 않고 해결되는지 먼저 시도합니다)

  비밀번호:  root

BANNER
read -p "진행하려면 엔터, 취소하려면 Ctrl-C ..."
echo

ssh -tt -o ConnectTimeout=10 -o ConnectionAttempts=5 -o StrictHostKeyChecking=accept-new \
  pollen@192.168.45.147 'bash -s' <<'REMOTE'
URL="https://media.githubusercontent.com/media/pollen-robotics/reachy_mini/main/src/reachy_mini/assets/firmware/reachymini_ua_io16_lin_v2.1.4.bin"
OUT=/tmp/fw_2.1.4.bin
WANT=803c9174f0ddb8bca9bc7fd5418c2051b720391ea6a0c4f77b36267b368446c7

echo "=== 1. USB 경로 찾기 ==="
DEV=""
for d in /sys/bus/usb/devices/*; do
  [ -f "$d/idVendor" ] || continue
  if [ "$(cat $d/idVendor 2>/dev/null)" = "38fb" ]; then
    DEV=$(basename "$d"); break
  fi
done
if [ -z "$DEV" ]; then echo "  Pollen 오디오 장치를 못 찾았습니다"; exit 1; fi
echo "  장치: $DEV"

echo
echo "=== 2. USB 리셋 (unbind → 3초 → bind) ==="
echo "$DEV" | sudo tee /sys/bus/usb/drivers/usb/unbind >/dev/null 2>&1 && echo "  unbind 완료" || echo "  unbind 실패"
sleep 3
echo "$DEV" | sudo tee /sys/bus/usb/drivers/usb/bind >/dev/null 2>&1 && echo "  bind 완료" || echo "  bind 실패"
sleep 5
echo "  재인식:"; lsusb | grep -i pollen || echo "    아직"

echo
echo "=== 3. 펌웨어 준비 ==="
if [ ! -f "$OUT" ] || [ "$(sha256sum $OUT 2>/dev/null | awk '{print $1}')" != "$WANT" ]; then
  echo "  내려받는 중..."
  curl -sSL "$URL" -o "$OUT"
fi
GOT=$(sha256sum "$OUT" | awk '{print $1}')
if [ "$GOT" != "$WANT" ]; then echo "  해시 불일치 — 중단"; exit 1; fi
echo "  검증 통과 ($(stat -c%s $OUT) 바이트)"

echo
echo "=== 4. 플래시 ==="
sudo dfu-util -R -e -a 1 -D "$OUT" || {
  echo
  echo "  ▶ 여전히 실패했습니다. 로봇 전원을 껐다 켠 뒤 다시 실행해 주세요."
  exit 1
}

echo
echo "=== 5. 재기동 대기 (20초) ==="
sleep 20
lsusb | grep -i pollen || echo "  아직 USB 재인식 전"

echo
echo "=== 6. 녹음 재시험 ==="
arecord -D reachymini_audio_src -f S16_LE -r 16000 -c 2 -d 2 /tmp/mictest4.wav 2>&1 | tail -1
python3 - <<'PY'
import wave, array
try:
    w = wave.open('/tmp/mictest4.wav')
    a = array.array('h'); a.frombytes(w.readframes(w.getnframes()))
    peak = max(abs(x) for x in a)
    print(f'  최대진폭 {peak} / 32767')
    print('  ▶ 여전히 무음 — 하드웨어로 확정' if peak < 50 else '  ▶ 신호 있음 — 마이크 복구 성공!')
except Exception as e:
    print('  읽기 실패:', e)
PY
exit
REMOTE

echo
echo "────────────────────────────────────────────────"
echo "  결과를 복사해서 Claude 에 붙여넣어 주세요."
echo "────────────────────────────────────────────────"
echo
read -p "엔터를 누르면 창이 닫힙니다..."
