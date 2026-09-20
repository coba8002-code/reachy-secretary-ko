#!/bin/bash
# 로봇에 저장된 키로 Gemini 한국어 응답 품질과 지연을 잰다.
cd /home/pollen/secretary
./.venv/bin/python - <<'PY'
import json, time, sys, urllib.request, urllib.error
from pathlib import Path

cfg = Path.home()/".local/share/reachy-secretary/config.json"
s = json.loads(cfg.read_text())
key = (s.get("keys") or {}).get("gemini")
model = s.get("model") or "gemini-3.6-flash"
if not key:
    print("  Gemini 키가 없습니다"); sys.exit(1)

SYSTEM = ("당신은 한국어 비서입니다. 음성으로 읽히므로 마크다운을 쓰지 말고, "
          "두 문장 이내로 짧게 답하세요. 숫자와 시각은 읽는 대로 쓰세요.")

tests = ["오늘 기분 어때?", "지금 오후 세 시 반인데 뭐 하면 좋을까?", "고마워"]
url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

for q in tests:
    payload = {
        "contents": [{"role":"user","parts":[{"text": q}]}],
        "systemInstruction": {"parts":[{"text": SYSTEM}]},
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type":"application/json"}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
        dt = time.time()-t0
        txt = d["candidates"][0]["content"]["parts"][0]["text"].strip()
        print(f'  [{dt:.2f}초] "{q}"')
        print(f'        → {txt}')
    except urllib.error.HTTPError as e:
        print(f'  실패 "{q}": HTTP {e.code} {e.read()[:150].decode("utf-8","replace")}')
    except Exception as e:
        print(f'  실패 "{q}": {type(e).__name__}: {e}')
PY
