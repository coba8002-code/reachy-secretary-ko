# Support request — Reachy Mini Wireless microphone returns silence

**Where to send**
- Warranty / replacement parts: **sales@pollen-robotics.com**
- Technical discussion: **Discord** https://discord.gg/Y7FgMqHsub

Send to sales@ for a replacement part; the evidence below is what their
after-sales team needs to classify it as a hardware defect. Attach your order
or invoice number — they ask for it every time.

---

Subject: Reachy Mini Wireless — microphone returns silence, not fixed by audio firmware 2.1.4

Hello,

My Reachy Mini Wireless captures no microphone signal at all. Speaker output,
motors and camera all work normally. I have worked through the troubleshooting
guide and updated the audio firmware, which did not help, so I believe this is
a hardware fault and would like to ask about a replacement microphone FPC cable
under warranty.

**Unit**

- Reachy Mini Wireless (CM4)
- Hardware ID: `4bbf5f6dbd06382c`
- Daemon version: 1.10.0 (the unit shipped on 1.11.0-rc.1; I moved it to the
  stable release while troubleshooting)
- Audio board (XVF3800) firmware: **2.1.4** — updated from 2.1.2 during this
  investigation, using the official binary and the command from
  `assets/firmware/update.sh`
- Order / invoice number: _[여기에 주문번호를 적어 주세요]_

**Symptom**

The microphone produces no acoustic signal. The audio interface is alive and
clocking — recordings come back the right length at the right sample rate — but
every sample sits at the noise floor.

**Measurements**

Five independent methods, all agreeing:

| Method | Result |
|---|---|
| `GET /api/state/doa`, 300 samples over 4 conditions (before firmware update) | `speech_detected` always false; `angle` frozen at exactly 1.5708 rad in every sample |
| Raw PCM via sounddevice, 25 s recording | peak amplitude **1 / 32767**, 86% of samples at ±1 |
| Official `reachy_mini_testbench` → `/api/hardware/mic_check` | **peak_db −90.3**, rms_db −90.7, `sound_detected: false` |
| `arecord -D reachymini_audio_src` on the robot itself, 1 s | peak amplitude **1 / 32767** |
| `GET /api/state/doa`, 80 samples **after** updating to firmware 2.1.4 | `speech_detected` always false; `angle` frozen at 0.0 |

A working microphone array shows at least some jitter in the DoA estimate from
ambient noise. A completely frozen angle across hundreds of samples, combined
with a −90 dB noise floor in the raw PCM, points to no signal reaching the
audio interface at all.

**What is working**

- Speaker: `POST /api/volume/test-sound` is clearly audible, and uploaded WAV
  files play correctly
- USB enumeration: `Bus 001 Device 003: ID 38fb:1001 Pollen Robotics Reachy Mini Audio`
- ALSA device: `card 0: Audio [Reachy Mini Audio], device 0: USB Audio`
- XVF3800 control interface: responds to parameter reads —
  `AUDIO_MGR_MIC_GAIN = 90`, `PP_AGCONOFF = 1`, `PP_AGCMAXGAIN = 10`,
  `PP_AGCDESIREDLEVEL = 0.0045`, `AUDIO_MGR_REF_GAIN = 8`
- `~/.asoundrc` is present
- Camera, motors and emotion playback all behave normally

**What I have ruled out**

- Microphone volume: 100% (`/api/volume/microphone/current`)
- Stale software: daemon moved from 1.11.0-rc.1 to stable 1.10.0
- Corrupted app state: conversation app removed and reinstalled from the
  official Space
- **Audio firmware: updated 2.1.2 → 2.1.4.** The 2.1.4 changelog mentions
  "Fixes the microphone not outputting sound after a usb reset", which matched
  my symptom exactly, so this was my main hypothesis. The update applied
  cleanly and `VERSION` now reads `2.1.4`, but the microphone is unchanged.
- Power cycling: the robot has been fully restarted several times

**Question**

Given that the audio board answers control commands and the speaker path works,
but no acoustic signal ever reaches the interface, the troubleshooting guide's
"the FPC cable of the microphone is damaged" seems the likely cause.

Could you confirm whether this unit is covered for a replacement microphone FPC
cable? I am comfortable doing the swap myself following your guide if you can
send the part — but I wanted to check with you before opening the head, in case
that affects the warranty.

Happy to run any further diagnostics you would like.

Thank you,

---

## 보내기 전에 확인하실 것

1. **주문번호 또는 인보이스 번호**를 위 자리에 넣으세요. 보증 처리에 반드시 필요합니다.
2. 이름과 연락처를 마지막에 덧붙이세요.
3. 가능하면 로봇 사진 한 장(전체 모습)을 첨부하면 처리가 빠릅니다.

## 왜 이 내용이면 충분한가

지원팀이 보통 되묻는 것들을 미리 다 막아두었습니다.

- *"최신 소프트웨어인가요?"* → 데몬 1.10.0 정식, 오디오 펌웨어 2.1.4 명시
- *"재부팅해 보셨나요?"* → 여러 번 했다고 명시
- *"볼륨 확인하셨나요?"* → 100% 명시
- *"앱 문제 아닌가요?"* → 재설치했고, ALSA 직접 녹음에서도 동일
- *"정말 마이크 문제인가요?"* → 서로 다른 5가지 측정이 같은 결론

그리고 **직접 열기 전에 물어본다**는 점을 분명히 해서, 보증이 무효가 되는 상황을 피했습니다.
