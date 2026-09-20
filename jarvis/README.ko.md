# Reachy Jarvis — 1단계: 알림 로봇

Claude Code가 **승인을 기다릴 때**와 **긴 작업을 끝냈을 때**, Reachy Mini가 한국어로 알려줍니다.

터미널을 계속 쳐다보지 않아도 되는 게 목적입니다. 자리를 비웠다가 돌아와 보니
30분째 권한 승인 대기 중이었던 경험이 있다면, 그걸 없애는 물건입니다.

**로봇 마이크가 없어도 동작합니다.** 로봇이 말하는 쪽만 쓰기 때문입니다.

---

## 동작

| 상황 | 로봇 |
|---|---|
| Claude가 **권한 승인 대기** | "승인이 필요합니다" + 묻는 동작 |
| 입력 대기 상태로 멈춤 | "기다리고 있습니다" |
| **긴 작업** 완료 (기본 45초 이상) | "작업이 끝났습니다" + 뿌듯한 동작 |
| 답이 분량 제한에 걸림 | "중간에 끊겼어요" + 당황한 동작 |
| **짧은 작업** 완료 | 🔇 침묵 |

짧은 작업에 침묵하는 게 핵심입니다. 매 응답마다 떠들면 사흘 만에 귀에서 지워지고,
정작 중요한 알림도 같이 묻힙니다.

각 문구는 3~4가지로 돌려 씁니다. 같은 문장만 반복하면 똑같이 무시하게 됩니다.

---

## 설치

**1. 음성 생성 및 업로드** (최초 1회, 문구를 바꿀 때마다)

```bash
python3 ~/reachy-secretary-ko/jarvis/prepare.py
```

macOS 내장 TTS(`Yuna`)로 12개 클립을 만들어 로봇에 올립니다. 다른 목소리를 쓰려면:

```bash
python3 ~/reachy-secretary-ko/jarvis/prepare.py --list-voices
python3 ~/reachy-secretary-ko/jarvis/prepare.py --voice Sandy --rebuild
```

**2. 훅 등록**

`jarvis/settings.snippet.json` 의 `hooks` 내용을 `~/.claude/settings.json` 에 합칩니다.
해당 파일에 이미 `hooks` 항목이 있다면 그 안에 이벤트를 추가하세요.

**3. Claude Code 재시작**

---

## 설정

환경변수로 조절합니다.

| 변수 | 기본값 | 의미 |
|---|---|---|
| `REACHY_HOST` | `192.168.45.147` | 로봇 IP |
| `REACHY_PORT` | `8000` | 데몬 포트 |
| `REACHY_TIMEOUT` | `3.0` | HTTP 타임아웃(초) |
| `REACHY_JARVIS_MIN_SECONDS` | `45` | 이 시간 이상 걸린 작업만 완료를 알림 |
| `REACHY_JARVIS_COOLDOWN` | `8` | 최소 발화 간격(초) |

로봇 IP가 바뀌면 `REACHY_HOST`를 설정하세요. 로봇의 `/api/daemon/status` 응답에
`wlan_ip` 로 현재 주소가 나옵니다.

문구와 동작을 바꾸려면 `phrases.py` 를 수정하고 `prepare.py` 를 다시 실행하세요.

---

## 설계상 지킨 것

**Claude Code를 절대 막지 않습니다.** 로봇이 꺼져 있든, 네트워크가 끊겼든,
입력이 깨졌든 `notify.py` 는 항상 종료코드 0으로 조용히 끝납니다. 알림 장치 때문에
작업이 멈추는 건 말이 안 됩니다. 훅도 `async: true` 로 등록해 백그라운드로 돕니다.

**미리 합성해 둡니다.** 알림마다 TTS를 돌리고 업로드하면 몇 초가 걸립니다.
그 비용을 설치 시점에 한 번만 치르고, 훅은 "이 파일 재생해" 한 번만 보냅니다.

**로봇이 재부팅되면 스스로 복구합니다.** 데몬은 음성 파일을 `/tmp` 에 보관해서
재부팅하면 사라집니다. `notify.py` 가 이를 감지해 로컬 캐시에서 다시 올리고,
캐시도 없으면 백그라운드로 `prepare.py` 를 돌립니다.

**의존성이 없습니다.** 표준 라이브러리만 씁니다. 훅은 매번 새 프로세스로
실행되므로 임포트가 가벼워야 합니다.

---

## 확인

로봇을 켜둔 채로 아래를 실행하면 실제로 말합니다.

```bash
echo '{"hook_event_name":"Notification","session_id":"t","notification_type":"permission_prompt"}' \
  | python3 ~/reachy-secretary-ko/jarvis/notify.py
```

소리가 안 나면 순서대로 확인하세요.

```bash
curl -s http://192.168.45.147:8000/api/daemon/status   # 로봇 살아있나
curl -s http://192.168.45.147:8000/api/media/sounds    # 음성 파일 올라가 있나
curl -s -X POST http://192.168.45.147:8000/api/volume/test-sound  # 스피커 되나
```

---

## 다음 단계

2단계는 **로봇 마이크 복구**(오디오 보드 펌웨어 2.1.4), 3단계는 **음성으로 지시하기**입니다.
3단계가 되면 "계속 진행해", "승인할게" 같은 말로 세션을 조종할 수 있고,
저장소 루트의 한국어 비서 인격과 툴이 거기에 붙습니다.
