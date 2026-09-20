# Reachy Mini 한국어 비서

*[English README →](README.md)*

Reachy Mini Wireless를 한국어로 대화하는 개인 비서로 만드는 설정 묶음입니다.

바닥부터 만들지 않습니다. Pollen Robotics의 공식 대화 앱
[`reachy_mini_conversation_app`](https://github.com/pollen-robotics/reachy_mini_conversation_app)
위에 **프로필 하나와 툴 네 개**를 얹는 방식입니다. 음성 인식, TTS, 감정 모션, 얼굴 추적,
장기기억, 웹 검색은 이미 그 앱에 있습니다.

## 무엇이 추가되나

| 파일 | 하는 일 |
|---|---|
| `profiles/secretary_ko/profile.md` | 한국어 비서 인격. 목소리 `Sohee`, 음성 출력에 맞춘 말투 규칙 |
| `external_tools/calendar_agenda.py` | 구글 캘린더 일정 읽기 (오늘 / 내일 / 이번 주) |
| `external_tools/calendar_add_event.py` | 구글 캘린더에 일정 등록 |
| `external_tools/gmail_digest.py` | Gmail 요약. 읽기 전용 |
| `external_tools/gmail_draft.py` | 메일 초안 작성. 본문은 Claude가 집필. 스레드 답장 지원. **발송은 하지 않음** |
| `external_tools/ask_claude.py` | 어려운 질문을 Claude Opus 5로 넘기는 '깊은 생각' 툴 |
| `external_tools/_secretary_lib/claude.py` | 위 두 툴이 공유하는 Claude 호출 모듈 |
| `authorize.py` | 구글 OAuth 1회 인증 (노트북에서 실행) |

이미 앱에 있어서 **따로 만들지 않은 것**: 기억(`remember`/`forget`), 웹 검색, 날씨, 시간,
감정 표현(82종), 춤, 얼굴 추적, 숨쉬기 모션, 카메라 인식, 볼륨 조절.

---

## 1. 공식 대화 앱 설치

로봇(Raspberry Pi 5)에 SSH로 접속한 상태에서 진행합니다.
Reachy Mini SDK와 데몬이 먼저 설치되어 있어야 합니다.

```bash
git clone https://github.com/pollen-robotics/reachy_mini_conversation_app.git
cd reachy_mini_conversation_app
uv venv --python python3.12 .venv && source .venv/bin/activate && uv sync
```

## 2. 이 묶음을 앱 안에 배치

`reachy-secretary-ko` 폴더를 앱 디렉터리 안으로 복사합니다.

```bash
cp -r /경로/reachy-secretary-ko ./secretary
cp secretary/.env.example .env
```

## 3. 한국어 설정

`.env` 파일에서 경로를 방금 복사한 위치로 맞춥니다.

```bash
REALTIME_TRANSCRIPTION_LANGUAGE=ko
REACHY_MINI_CUSTOM_PROFILE=secretary_ko
REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY=./secretary/profiles
REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY=./secretary/external_tools
AUTOLOAD_EXTERNAL_TOOLS=1
REACHY_MINI_APP_TIMEOUT_MINUTES=0
```

### 여기서 먼저 한국어부터 확인하세요

툴을 붙이기 전에 **한국어가 실제로 되는지 확인하는 게 우선**입니다. 이게 안 되면
나머지는 의미가 없습니다. 이 상태로 바로 실행해 보세요.

```bash
reachy-mini-conversation-app --ui
```

확인할 것 두 가지입니다.

- **알아듣는가** — 한국어로 말을 걸었을 때 인식되는지. `REALTIME_TRANSCRIPTION_LANGUAGE`
  값은 앱이 검증 없이 백엔드로 그대로 넘기므로, `ko` 지원 여부는 허깅페이스 백엔드에 달려 있습니다.
- **한국어로 말하는가** — TTS 엔진은 Qwen3-TTS이고 `Sohee`는 한국어 화자입니다.
  발음이 어색하면 `profile.md`의 `voice` 값을 다른 것으로 바꿔가며 비교해 보세요.

둘 중 하나라도 안 되면 대안은 로컬 백엔드입니다.
[huggingface/speech-to-speech](https://github.com/huggingface/speech-to-speech)를
노트북에 띄우고 한국어 STT/TTS 모델을 직접 지정한 뒤, `.env`를 이렇게 바꿉니다.

```bash
HF_REALTIME_CONNECTION_MODE=local
HF_REALTIME_WS_URL=ws://<노트북-LAN-IP>:8765/v1/realtime
```

## 4. Claude 연결 (ask_claude)

[console.anthropic.com](https://console.anthropic.com)에서 API 키를 발급받아 `.env`에 넣습니다.

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

```bash
pip install anthropic
```

음성 백엔드는 응답 속도에 맞춰져 있어서 여러 단계를 따지는 추론에는 약합니다.
`ask_claude`는 그런 질문만 Claude Opus 5로 넘기는 우회로입니다. 빠른 대화 루프는
그대로 두고, 깊이가 필요한 몇 번의 턴만 위임합니다.

지연을 줄이려고 `effort`를 기본값 `high`가 아니라 `medium`으로 낮춰 두었습니다.
답이 얕게 느껴지면 `ask_claude.py`의 `output_config`에서 올리세요. 대신 침묵이 길어집니다.

## 5. 구글 연결 (캘린더 · 메일)

로봇에는 브라우저가 없으므로, **인증은 노트북에서 한 번만** 하고 결과 토큰만 옮깁니다.

**노트북에서:**

1. [Google Cloud Console](https://console.cloud.google.com)에서 프로젝트를 만들고
   Calendar API와 Gmail API를 활성화합니다.
2. 사용자 인증 정보 → OAuth 클라이언트 ID → **데스크톱 앱**으로 만들고 JSON을 내려받습니다.
3. 그 파일을 `credentials.json`이라는 이름으로 아래 위치에 둡니다.

```bash
mkdir -p ~/.local/share/reachy_secretary_ko
mv ~/Downloads/client_secret_*.json ~/.local/share/reachy_secretary_ko/credentials.json
```

```bash
pip install google-api-python-client google-auth-oauthlib
python3 secretary/authorize.py
```

브라우저에서 동의하면 `token.json`이 생깁니다. 이걸 로봇으로 복사합니다.

```bash
scp ~/.local/share/reachy_secretary_ko/token.json <로봇계정>@<로봇주소>:~/.local/share/reachy_secretary_ko/token.json
```

**로봇에서:**

```bash
pip install google-api-python-client google-auth-oauthlib
```

토큰은 만료돼도 자동 갱신되므로 이 과정은 한 번이면 됩니다.

### 권한 범위에 관해 — 꼭 읽어주세요

요청하는 권한은 세 가지입니다.

- 캘린더: `calendar.events` — 일정 읽기와 등록
- 메일: `gmail.readonly` — 받은편지함 읽기
- 메일: `gmail.compose` — 초안 작성

**`gmail.compose`에는 짚고 넘어갈 점이 있습니다.** 구글의 공식 설명은
"Manage drafts and **send emails**"입니다. 초안만 허용하고 발송은 막는 권한은
Gmail API에 존재하지 않습니다. 즉 이 토큰 자체는 기술적으로 메일을 보낼 수 있습니다.

이 묶음의 코드는 `drafts().send()`도 `messages().send()`도 **호출하지 않습니다.**
초안 생성만 합니다. 다만 그 보장은 구글 권한이 아니라 **코드가 지키는 약속**입니다.
차이가 있습니다. 직접 확인하시려면 이렇게 검사할 수 있습니다.

```bash
grep -rn "\.send(\|\.trash(\|\.delete(" secretary/external_tools/
```

호출이 하나도 나오지 않아야 정상입니다.

발송까지 구글 차원에서 막고 싶으시면 `google_auth.py`의 `SCOPES`에서 `gmail.compose`를
지우고 `gmail_draft.py`를 삭제하세요. 읽기와 요약만 남습니다.

> **이미 인증하셨다면 다시 해야 합니다.** 권한이 추가되었으므로 기존 `token.json`은
> 새 권한을 갖고 있지 않습니다. `authorize.py`를 다시 실행하고 토큰을 다시 복사하세요.

## 6. 실행

```bash
reachy-mini-conversation-app --ui
```

웹 UI는 http://127.0.0.1:7860 에서 열립니다. Home에서 `secretary_ko`를 선택하면 적용됩니다.

---

## 시험해 볼 말

| 말 | 동작 |
|---|---|
| "오늘 일정 뭐 있어?" | `calendar_agenda` |
| "내일 오후 3시에 치과 예약 잡아줘" | `calendar_add_event` |
| "메일 온 거 중에 중요한 거 있어?" | `gmail_digest` |
| "민수씨 메일에 답장 초안 써줘" | `gmail_digest` → `gmail_draft` (스레드 답장) |
| "김대리한테 회의 연기한다고 메일 써줘" | `gmail_draft` (주소 모르면 되물음) |
| "이 문제 어떻게 접근하는 게 좋을까?" | `ask_claude` |
| "나 커피 안 마셔" | `remember` (조용히 저장) |
| "지금 파리 몇 시야?" | 내장 time 툴 |

---

## 자비스 알림 로봇 (1단계)

Claude Code가 승인을 기다리거나 긴 작업을 끝냈을 때 로봇이 한국어로 알려줍니다.
**로봇 마이크 없이 동작합니다** — 말하는 쪽만 쓰기 때문입니다.

설치와 설정은 [jarvis/README.ko.md](jarvis/README.ko.md) 참고.

```bash
python3 jarvis/prepare.py          # 음성 합성 + 업로드 (최초 1회)
# jarvis/settings.snippet.json 을 ~/.claude/settings.json 에 병합
```

## 라이선스

[Apache License 2.0](LICENSE). 확장 대상인 공식 대화 앱과 같은 라이선스입니다.

## 알려진 한계

- **한국어 지원은 허깅페이스 백엔드에 달려 있습니다.** 이 묶음은 `ko`를 전달할 뿐이고,
  실제 인식 품질은 3단계에서 직접 확인해야 합니다. 이게 가장 큰 미검증 항목입니다.
- **메일 발송은 되지 않습니다.** 초안까지만 만들고, 보내는 건 사용자가 메일 앱에서 직접 합니다.
  되돌릴 수 없는 동작을 음성 한 마디로 실행하는 건 위험하다고 판단했습니다.
- **초안 본문은 Claude Opus 5가 씁니다.** 음성 모델은 "무슨 내용을 담을지"만 한 줄로 넘기고,
  실제 문장은 `gmail_draft`가 Claude를 직접 불러 만듭니다. 답장일 때는 원본 메일 본문까지
  읽고 씁니다. 따라서 `ANTHROPIC_API_KEY`가 없으면 초안 작성도 되지 않습니다
  (사용자가 문장을 그대로 불러준 경우는 예외).
- **Claude는 없는 사실을 지어내지 말고 `[확인 필요]`로 표시하도록 지시되어 있습니다.**
  초안을 보내기 전에 그 표시가 남아 있는지 확인하세요.
- **`ask_claude`는 대화 맥락을 자동으로 보지 못합니다.** 로봇이 `context` 인자에 필요한
  배경을 넣어 주어야 합니다. 프로필에서 그렇게 지시해 두었지만, 대명사를 그대로 넘기면
  Claude가 무엇을 가리키는지 알 수 없습니다.
- **툴 코드는 실물 하드웨어와 실제 구글 계정에서 아직 실행해 보지 않았습니다.**
  검증한 것: 문법, 앱의 툴 인터페이스 준수, Anthropic SDK 파라미터(1.7.0 기준),
  그리고 `gmail_draft`의 MIME 구성·한글 헤더 인코딩·스레드 답장 헤더는
  가짜 Gmail 서비스를 붙여 실제로 실행해 확인했습니다.
