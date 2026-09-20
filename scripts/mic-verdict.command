#!/bin/bash
# 마이크 최종 판정 — 무거운 앱 없이 ALSA 에 직접 붙어 녹음한다.
clear
cat <<'BANNER'
────────────────────────────────────────────────
  마이크 최종 판정
────────────────────────────────────────────────

  펌웨어  : 2.1.2 → 2.1.4  (적용 완료 확인됨)
  비교기준: 교체 전 같은 방식으로 잰 값 = 1 / 32767

  "지금 말하세요" 가 뜨면 로봇 가까이(30cm)에서
  5초간 또렷하게 말해주세요.

  비밀번호:  root

BANNER
read -p "진행하려면 엔터 ..."
echo

ssh -tt -o ConnectTimeout=15 -o ConnectionAttempts=5 -o StrictHostKeyChecking=accept-new \
  pollen@192.168.45.147 'bash -s' <<'REMOTE'
echo "=== USB 오디오 보드 ==="
lsusb | grep -i pollen || echo "  미인식"

echo
echo "=== 녹음 준비 (데몬이 장치를 잡고 있으면 잠시 비움) ==="
sudo systemctl stop reachy-mini-daemon 2>/dev/null
sleep 4

echo
echo "  ▶▶▶  지금 로봇에 대고 말하세요 (5초)  ◀◀◀"
sleep 1
arecord -D reachymini_audio_src -f S16_LE -r 16000 -c 2 -d 5 /tmp/verdict.wav 2>&1 | tail -1

echo
echo "=== 파형 분석 ==="
python3 - <<'PY'
import wave, array, math
try:
    w = wave.open('/tmp/verdict.wav')
    ch = w.getnchannels()
    a = array.array('h'); a.frombytes(w.readframes(w.getnframes()))
    if ch > 1: a = a[0::ch]
    peak = max(abs(x) for x in a)
    rms  = math.sqrt(sum(x*x for x in a)/len(a))
    db   = 20*math.log10(peak/32767) if peak else -99
    print(f"  샘플     : {len(a):,}")
    print(f"  최대진폭 : {peak} / 32767  ({db:.1f} dB)")
    print(f"  RMS      : {rms:.1f}")
    print(f"  교체 전  : 1 / 32767")
    print()
    print("  >>> 여전히 무음 - 하드웨어 문제로 확정" if peak < 50
          else "  >>> 신호 있음 - 마이크 복구 성공!")
except Exception as e:
    print("  분석 실패:", e)
PY

echo
echo "=== 데몬 복구 ==="
sudo systemctl start reachy-mini-daemon 2>/dev/null
sleep 6
systemctl is-active reachy-mini-daemon 2>/dev/null
exit
REMOTE

echo
echo "────────────────────────────────────────────────"
read -p "결과를 복사하신 뒤 엔터를 누르면 창이 닫힙니다..."
