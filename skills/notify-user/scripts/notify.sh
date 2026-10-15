#!/usr/bin/env bash
set -euo pipefail

fail() {
    printf 'notify-user: %s\n' "$*" >&2
    exit 1
}
usage='Usage: notify.sh [--title TITLE] "short message"'
title_arg=
if [[ ${1:-} == --title ]]; then
    [[ $# -eq 3 && -n $2 && -n $3 ]] || fail "$usage"
    # Same sanitizing as the message; a semicolon would split the payload.
    title_arg=$(printf '%s' "$2" | LC_ALL=C tr -d '\000-\037\177' | tr ';' ',')
    title_arg=${title_arg:0:60}
    [[ -n $title_arg ]] || fail 'Title is empty after sanitizing'
    shift 2
fi
[[ $# -eq 1 && -n $1 ]] || fail "$usage"
# Remove terminal control characters while preserving UTF-8 text.
message=$(printf '%s' "$1" | LC_ALL=C tr -d '\000-\037\177')
[[ -n $message ]] || fail 'Message is empty after sanitizing'
message=${message:0:240}
target=${NOTIFY_TTY:-}
wrapped=0

# Inside herdr, a pane's pty is consumed by herdr's own terminal emulator,
# which swallows OSC sequences, and herdr's notification API only renders
# in-app toasts. Write an OSC 777 notification (title + body; supported by
# Windows Terminal, kitty, WezTerm) directly to the TTY hosting each
# attached herdr TUI client instead: the sequence rides the TUI's output
# stream through SSH to the user's local terminal, which shows a desktop
# toast titled after the calling agent. The API call adds an in-app toast
# and sound as a secondary, best-effort channel.
if [[ ${TERM_PROGRAM:-} == herdr ]]; then
    # An explicit --title wins; otherwise title the toast after whichever
    # agent invoked this script, walking the ancestry because any agent
    # (claude, codex, ...) may call the skill.
    title=${title_arg:-Agent}
    if [[ -z $title_arg ]]; then
        pid=$PPID
        for ((depth = 0; depth < 16 && pid > 1; depth++)); do
        cmdline=$(ps -p "$pid" -o args= 2>/dev/null) || break
        # Tool shells carry the message text in their command line; skip
        # them so a message mentioning another agent cannot hijack the title.
        [[ $cmdline == *notify.sh* ]] && { read -r pid _ < <(ps -p "$pid" -o ppid=) || break; continue; }
        case "$cmdline" in
            *claude*) title='Claude Code'; break ;;
            *codex*) title='Codex'; break ;;
            *grok*) title='Grok'; break ;;
            *qwen*) title='Qwen Code'; break ;;
            *kimi*) title='Kimi'; break ;;
            *opencode*) title='OpenCode'; break ;;
            *cursor*) title='Cursor'; break ;;
        esac
        read -r pid _ < <(ps -p "$pid" -o ppid=) || break
        done
    fi
    # NOTIFY_TTY overrides discovery for an explicit transport test.
    message=${message//;/,} # a semicolon would split the OSC 777 payload
    if [[ -n $target ]]; then
        [[ $target == /dev/pts/[0-9]* || $target == /dev/tty[0-9]* ]] || fail 'NOTIFY_TTY must be a terminal device'
        [[ -c $target && -w $target && -O $target ]] || fail 'NOTIFY_TTY is not an owned writable device'
        printf '\033]777;notify;%s;%s\007' "$title" "$message" >"$target"
        printf 'notify-user: sequence written to %s (transport test)\n' "$target" >&2
        exit 0
    fi
    delivered=0
    while read -r tty; do
        target=/dev/$tty
        [[ -c $target && -w $target && -O $target ]] || continue
        printf '\033]777;notify;%s;%s\007' "$title" "$message" >"$target" && delivered=1
    done < <(ps -eo tty=,user=,args= | awk -v u="$(id -un)" '
        $1 ~ /^pts\/[0-9]+$|^tty[0-9]+$/ && $2 == u && ($3 == "herdr" || $3 ~ /\/herdr$/) {
            # Bare TUI, or one addressed to a session; exclude servers and
            # transient CLI calls (their extra args never match below).
            if (NF == 3 || ($4 == "--session" && NF == 5) || ($4 == "session" && $5 == "attach"))
                print $1
        }')
    # Secondary channel: in-app toast + sound. Best effort only.
    command -v herdr >/dev/null 2>&1 && \
        herdr notification show "$title" --body "$message" --sound done >/dev/null 2>&1 || true
    ((delivered)) || fail 'No herdr TUI terminal found for OSC delivery'
    printf 'notify-user: OSC 777 written to herdr TUI tty(s)\n' >&2
    exit 0
fi

if [[ -n ${TMUX:-} ]]; then
    [[ -n ${TMUX_PANE:-} ]] || fail 'TMUX_PANE is missing'
    session=$(tmux display-message -p -t "$TMUX_PANE" '#{session_id}')
    [[ -n $(tmux list-clients -t "$session" -F '#{client_tty}') ]] || fail 'No attached tmux client; notification was not sent'
    target=$(tmux display-message -p -t "$TMUX_PANE" '#{pane_tty}')
    mode=$(tmux show-options -wv -t "$TMUX_PANE" allow-passthrough)
    if [[ $mode != on && $mode != all ]]; then
        tmux set-option -w -t "$TMUX_PANE" allow-passthrough on
    fi
    wrapped=1
elif [[ -z $target ]]; then
    # Tool commands may have their own captured PTY. Walk outward to the
    # terminal hosting the agent instead of writing to that temporary PTY.
    pid=$PPID
    for ((depth = 0; depth < 64 && pid > 1; depth++)); do
        read -r parent terminal < <(ps -p "$pid" -o ppid= -o tty=) || break
        [[ $terminal != '?' && -n $terminal ]] && target=/dev/$terminal
        [[ $parent =~ ^[0-9]+$ && $parent != "$pid" ]] || break
        pid=$parent
    done
fi

[[ $target == /dev/pts/[0-9]* || $target == /dev/tty[0-9]* ]] || fail 'No originating terminal found'
[[ -c $target && -w $target && -O $target ]] || fail 'Originating terminal is not an owned writable device'
if ((wrapped)); then
    printf '\033Ptmux;\033\033]9;%s\007\033\\' "$message" >"$target"
else
    printf '\033]9;%s\007' "$message" >"$target"
fi
printf 'notify-user: sequence written to %s (toast display is not acknowledged)\n' "$target" >&2
