---
name: notify-user
description: Use when a long task finishes, a consequential milestone is ready, user input is required, or an important failure needs attention; skip short routine work.
---

# Notify user

Notify when the user's attention would be useful independently of terminal focus: after substantial work completes, when a usable milestone is ready, or when progress needs input or intervention. Continue useful independent work first.

Skip routine commands, short answers, minor steps, resolved transient failures, and repeated reminders. Send at most one notification per meaningful event and respect requests for silence.

Use one short sentence in the user's language, without secrets or verbose logs. Run the bundled script by resolving it relative to this skill directory:

```sh
bash <skill-directory>/scripts/notify.sh 'Task finished; results are ready.'
bash <skill-directory>/scripts/notify.sh --title 'Build finished' 'All tests passed.'
```

An optional `--title` names the notification; without it, inside herdr the title defaults to the calling agent (Claude Code, Codex, ...). Titles and messages are sanitized and truncated (60/240 chars).

The script routes OSC 9 to the originating terminal. In tmux it uses `TMUX_PANE`; outside tmux it follows process ancestry. Inside herdr it writes OSC 777 directly to the terminal of each attached herdr TUI client (routed through SSH to the user's local terminal) and fires a herdr in-app toast as well. Never select another user's terminal or guess an unrelated pane. `NOTIFY_TTY` may select a verified originating terminal for a transport test.

An attached terminal with an OSC notification receiver is required. If delivery fails, do not retry repeatedly or change unrelated settings. Successful execution proves that the sequence was written, not that a desktop toast appeared. Always provide the normal final response or question too.
