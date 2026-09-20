#!/bin/bash
# 로봇에 한국어 음성 합성을 설치한다.
#
# 로봇에는 say 도 espeak 도 없다. 맥의 음성 엔진을 쓰면 맥이 켜져 있어야
# 로봇이 새 문장을 말할 수 있는데, 그건 이 비서가 절대 의존하면 안 되는
# 조건이다. 그래서 음성 모델을 로봇 안에 둔다.
set -e

ROOT="${1:-$HOME/secretary}"
VOICE_DIR="$ROOT/voices/ko_KR-kss-medium"
BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/ko/ko_KR/kss/medium

echo "=== 1. piper 설치 ==="
"$ROOT/.venv/bin/pip" install -q piper-tts
echo "  완료"

echo
echo "=== 2. 한국어 음성 모델 (63MB) ==="
mkdir -p "$VOICE_DIR"
for f in ko_KR-kss-medium.onnx ko_KR-kss-medium.onnx.json; do
    if [ -s "$VOICE_DIR/$f" ]; then
        echo "  $f 이미 있음"
    else
        curl -sL --fail -o "$VOICE_DIR/$f" "$BASE/$f"
        echo "  $f 받음"
    fi
done

echo
echo "=== 3. 확인 ==="
cd "$ROOT" && ./.venv/bin/python -c "
import sys; sys.path.insert(0, 'jarvis')
import tts
print('  엔진:', tts.engine())
print('  모델:', tts.VOICE_PATH)
"

echo
echo "=== 완료 ==="
echo "  이제 맥 없이 로봇 혼자 한국어를 말할 수 있습니다."
