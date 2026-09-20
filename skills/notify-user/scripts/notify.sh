#!/usr/bin/env bash
set -euo pipefail

fail() {
    printf 'notify-user: %s\n' "$*" >&2
    exit 1
}
[[ $# -eq 1 && -n $1 ]] || fail 'Usage: notify.sh "short message"'
# Remove terminal control characters while preserving UTF-8 text.
message=$(printf '%s' "$1" | LC_ALL=C tr -d '\000-\037\177')
[[ -n $message ]] || fail 'Message is empty after sanitizing'
message=${message:0:240}
target=${NOTIFY_TTY:-}
wrapped=0

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
