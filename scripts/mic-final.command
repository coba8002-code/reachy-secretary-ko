#!/bin/bash
# 펌웨어 2.1.4 적용 후 마이크 최종 확인.
# sudo 없이, 데몬을 건드리지 않고, ALSA 에 직접 붙어 녹음한다.
# 오늘 아침 첫 진단과 완전히 같은 조건이라 교체 전후를 그대로 비교할 수 있다.
clear
cat <<'BANNER'
────────────────────────────────────────────────
  마이크 최종 확인
────────────────────────────────────────────────

  펌웨어  : 2.1.2 -> 2.1.4  (적용 완료)
  비교기준: 교체 전 같은 방식으로 잰 값 = 1 / 32767

  "지금 말하세요" 가 뜨면 로봇 30cm 이내에서
  5초간 또렷하게 말해주세요.

  비밀번호:  root

BANNER
read -p "진행하려면 엔터 ..."
echo

ssh -o ConnectTimeout=15 -o ConnectionAttempts=5 -o StrictHostKeyChecking=accept-new \
  pollen@192.168.45.147 'bash -s' <<'REMOTE'
echo "=== USB 오디오 보드 ==="
lsusb | grep -i pollen

echo
echo "=== 오디오 입력 장치 ==="
arecord -l | grep '^card'

echo
echo "=== 3초 뒤 5초간 녹음합니다 ==="
sleep 3
echo "  >>> 지금 로봇에 대고 말하세요 <<<"
arecord -D reachymini_audio_src -f S16_LE -r 16000 -c 2 -d 5 /tmp/final.wav 2>&1 | tail -1

echo
echo "=== 파형 분석 ==="
python3 - <<'PY'
import wave, array, math
try:
    w = wave.open('/tmp/final.wav')
    ch = w.getnchannels()
    a = array.array('h'); a.frombytes(w.readframes(w.getnframes()))
    if ch > 1: a = a[0::ch]
    peak = max(abs(x) for x in a)
    rms  = math.sqrt(sum(x*x for x in a)/len(a))
    db   = 20*math.log10(peak/32767) if peak else -99
    print(f"  샘플     : {len(a):,}")
    print(f"  최대진폭 : {peak} / 32767   ({db:.1f} dB)")
    print(f"  RMS      : {rms:.2f}")
    print()
    print("  교체 전 (2.1.2) : 1 / 32767")
    print(f"  교체 후 (2.1.4) : {peak} / 32767")
    print()
    if peak < 50:
        print("  >>> 여전히 무음 - 마이크 하드웨어 문제로 최종 확정")
        print("      FPC 케이블 교체가 필요합니다. 지원 문의는 이미 발송했습니다.")
    else:
        print("  >>> 신호 있음 - 마이크가 살아났습니다!")
except Exception as e:
    print("  분석 실패:", e)
PY

echo
echo "=== 1초 단위 레벨 ==="
python3 - <<'PY'
import wave, array
try:
    w = wave.open('/tmp/final.wav'); ch=w.getnchannels(); sr=w.getframerate()
    a = array.array('h'); a.frombytes(w.readframes(w.getnframes()))
    if ch>1: a=a[0::ch]
    for s in range(5):
        seg = a[s*sr:(s+1)*sr]
        if not seg: break
        p = max(abs(x) for x in seg)
        print(f"   {s}s |{'#'*min(int(p/400),50)} {p}")
except Exception as e:
    print("  실패:", e)
PY
REMOTE

echo
echo "────────────────────────────────────────────────"
echo "  결과를 Claude 에 붙여넣어 주세요."
echo "────────────────────────────────────────────────"
read -p "엔터를 누르면 창이 닫힙니다..."
