# Reachy Mini Korean Secretary

Turn a Reachy Mini into a Korean-speaking personal assistant that handles your calendar, your inbox, and the questions your voice model isn't smart enough to answer.

*[한국어 설치 가이드 →](README.ko.md)*

---

## What this is

This is **not** a standalone app. It is a profile and a set of tools that drop into
[`pollen-robotics/reachy_mini_conversation_app`](https://github.com/pollen-robotics/reachy_mini_conversation_app),
the official conversation app.

That app already handles speech recognition, text-to-speech, emotion playback, face tracking,
long-term memory, and web search. There is no reason to rebuild any of it. This repository adds
the secretary half and the Korean half, and nothing else.

## What it adds

| File | What it does |
|---|---|
| `profiles/secretary_ko/` | Korean assistant persona. Voice `Sohee`, with speech-shaped output rules |
| `external_tools/calendar_agenda.py` | Read Google Calendar — today, tomorrow, or the week ahead |
| `external_tools/calendar_add_event.py` | Create a calendar event |
| `external_tools/gmail_digest.py` | Summarize recent inbox mail, bulk mail filtered out. Read-only |
| `external_tools/gmail_draft.py` | Write an email draft. Body composed by the judgement model. Threaded replies |
| `external_tools/deep_think.py` | Hand reasoning-heavy turns to whichever model holds the judgement role |
| `authorize.py` | One-time Google OAuth, run on a machine with a browser |

## Two design decisions worth knowing

**The robot cannot send email.** It drafts, and the draft waits in your Drafts folder until you
send it yourself. Sending is irreversible, and a spoken sentence is a thin gate for something
irreversible.

Be aware of what that guarantee rests on: Google publishes `gmail.compose` as *"Manage drafts and
send emails"*, and there is no drafts-only Gmail scope. The token is technically capable of
sending; the code simply never calls a send endpoint. That is a promise kept by this codebase, not
by Google. You can check it yourself:

```bash
grep -rn "\.send(\|\.trash(\|\.delete(" external_tools/
```

It should return nothing. To have Google enforce it instead, drop `gmail.compose` from `SCOPES` in
`external_tools/_secretary_lib/google_auth.py` and delete `gmail_draft.py`.

**The voice model does not write your email.** Realtime voice backends are tuned for short spoken
turns, and relaying a paragraph of prose through a tool argument is what they are worst at. The
robot passes a one-line brief; Claude Opus 5 writes the actual prose, reading the original message
first when it is a reply. Claude is instructed never to invent dates, amounts, or commitments — it
leaves a visible `[확인 필요]` marker instead, and the robot is told to point those out.

## Requirements

- Reachy Mini (built for the Wireless version; Lite should work with the app running on the host)
- The official conversation app, installed and running
- Python 3.12
- An API key for at least one provider — Gemini, Claude, OpenAI or Grok. The admin panel assigns
  which one does chat, judgement and speech-to-text; `deep_think` and draft composition follow the
  judgement role
- A Google Cloud project with the Calendar and Gmail APIs enabled

## Quick start

```bash
# 1. inside your reachy_mini_conversation_app checkout
cp -r /path/to/reachy-secretary-ko ./secretary
cp secretary/.env.example .env

# 2. point .env at the copied directories, then
reachy-mini-conversation-app --ui
```

Full walkthrough, including Google OAuth on a headless robot: **[README.ko.md](README.ko.md)**.

### Verify Korean first

Before wiring up any tools, confirm the robot actually understands and speaks Korean. If it does
not, nothing else matters. Set `REALTIME_TRANSCRIPTION_LANGUAGE=ko`, pick the `Sohee` voice, and
just talk to it. Fallback options are in the Korean guide.

## Known limitations

- **Korean support depends on the Hugging Face realtime backend.** This repository passes `ko`
  through; whether the backend honors it is the single biggest unverified assumption here.
- **No email sending or deletion.** By design, as above.
- **`deep_think` cannot see the conversation.** The robot has to supply context explicitly. The
  profile instructs it to, but pronouns passed through verbatim will not resolve.
- **Not yet run against real hardware or a real Google account.** Verified so far: syntax, the
  app's tool interface contract, Anthropic SDK parameters against v1.7.0, and `gmail_draft`'s MIME
  assembly, Korean header encoding, and reply threading against a stubbed Gmail service.

## Jarvis notifier (stage 1)

Reachy Mini announces, in Korean, when Claude Code is blocked waiting for your
approval and when a long task finishes — so you can stop watching the terminal.
Short turns stay silent on purpose; a robot that comments on everything gets
tuned out, and the announcements that matter get lost with it.

It needs no microphone — only the speaker and motors, which work independently
of the mic fault described above. Setup: [jarvis/README.ko.md](jarvis/README.ko.md).

## License

[Apache License 2.0](LICENSE) — the same license as the upstream conversation app this extends.

## Credits

Built on [Reachy Mini](https://github.com/pollen-robotics/reachy_mini) and the
[conversation app](https://github.com/pollen-robotics/reachy_mini_conversation_app) by
Pollen Robotics (Apache 2.0). Emotion and dance motion come from their open datasets.
