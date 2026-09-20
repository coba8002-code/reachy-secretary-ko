#!/bin/bash
# USB 마이크를 로봇의 기본 입력으로 연결한다.
#
# 데몬과 대화 앱은 모두 ALSA 이름 'reachymini_audio_src' 로 마이크를 찾는다.
# 그 이름이 USB 마이크를 가리키게 바꾸면 앱 코드를 건드리지 않아도 된다.
# 스피커 이름은 손대지 않으므로 소리는 계속 로봇에서 난다.
clear
cat <<'BANNER'
────────────────────────────────────────────────
  USB 마이크 연결
────────────────────────────────────────────────

  먼저 USB 마이크를 로봇에 꽂아주세요.
  꽂으신 뒤에 엔터를 누르세요.

  하는 일:
    1. 연결된 오디오 입력 장치 목록 확인
    2. 기존 .asoundrc 백업
    3. reachymini_audio_src 를 USB 마이크로 재지정
    4. 실제 녹음해서 소리가 들어오는지 확인

  원복은 언제든 가능합니다 (백업 파일이 남습니다).

  비밀번호:  root

BANNER
read -p "USB 마이크를 꽂으셨으면 엔터 ..."
echo

ssh -tt -o ConnectTimeout=15 -o ConnectionAttempts=5 -o StrictHostKeyChecking=accept-new \
  pollen@192.168.45.147 'bash -s' <<'REMOTE'
echo "=== 1. USB 장치 목록 ==="
lsusb

echo
echo "=== 2. 오디오 입력 장치 ==="
arecord -l

echo
echo "=== 3. 현재 .asoundrc ==="
cp -n ~/.asoundrc ~/.asoundrc.original 2>/dev/null && echo "  원본 백업: ~/.asoundrc.original"
cat ~/.asoundrc

echo
echo "=== 4. 내장 마이크가 아닌 카드 찾기 ==="
arecord -l | grep '^card' | grep -v -i "Reachy Mini Audio" || echo "  (내장 외 입력 장치가 보이지 않습니다)"

echo
echo "────────────────────────────────────────"
echo "위 목록에서 USB 마이크의 card 번호를 확인하세요."
echo "예:  card 1: Device [USB PnP Audio Device]  ->  카드 번호 1"
echo
echo "확인하셨으면 아래를 실행하면 됩니다 (N 을 카드 번호로 바꾸세요):"
echo
echo "  ~/set-usb-mic.sh N"
echo "────────────────────────────────────────"

cat > ~/set-usb-mic.sh <<'SETUP'
#!/bin/bash
# reachymini_audio_src 를 지정한 카드의 USB 마이크로 재지정한다.
set -e
CARD="$1"
[ -z "$CARD" ] && { echo "사용법: ~/set-usb-mic.sh <카드번호>"; exit 1; }

cp -n ~/.asoundrc ~/.asoundrc.original 2>/dev/null || true
cp ~/.asoundrc ~/.asoundrc.bak.$(date +%s)

python3 - "$CARD" <<'PY'
import re, sys, pathlib
card = sys.argv[1]
p = pathlib.Path.home() / ".asoundrc"
text = p.read_text()

block = f"""
# --- USB 마이크로 재지정 (reachy-secretary) ---
# 원본은 ~/.asoundrc.original 에 있습니다. 되돌리려면:
#   cp ~/.asoundrc.original ~/.asoundrc
pcm.reachymini_audio_src {{
    type plug
    slave.pcm "hw:{card},0"
}}
"""

# 기존 정의를 주석 처리하고 새 정의를 덧붙인다.
text = re.sub(r'(?m)^(pcm\\.reachymini_audio_src\\s*\\{)', r'#\\1', text)
p.write_text(text + block)
print(f"  reachymini_audio_src -> hw:{card},0 로 재지정")
PY

echo
echo "  5초 녹음 시험 — 지금 말하세요"
sleep 1
arecord -D reachymini_audio_src -f S16_LE -r 16000 -c 1 -d 5 /tmp/usbmic.wav 2>&1 | tail -1
python3 - <<'PY'
import wave, array, math
w = wave.open('/tmp/usbmic.wav')
a = array.array('h'); a.frombytes(w.readframes(w.getnframes()))
peak = max(abs(x) for x in a); rms = math.sqrt(sum(x*x for x in a)/len(a))
print(f"  최대진폭 {peak} / 32767   RMS {rms:.1f}")
print("  >>> 무음 - 카드 번호를 다시 확인하세요" if peak < 50 else "  >>> 소리 들어옴 - 성공!")
PY

echo
echo "  데몬 재시작"
sudo systemctl restart reachy-mini-daemon
SETUP
chmod +x ~/set-usb-mic.sh
echo
echo "  (~/set-usb-mic.sh 를 로봇에 만들어 두었습니다)"
exit
REMOTE

echo
echo "────────────────────────────────────────────────"
echo "  위 출력을 Claude 에 붙여넣어 주세요."
echo "────────────────────────────────────────────────"
read -p "엔터를 누르면 창이 닫힙니다..."
