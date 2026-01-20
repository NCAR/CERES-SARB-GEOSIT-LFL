#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 [PIDFILE]" >&2
    echo "" >&2
    echo "Kills all running jobs from a daily processing run." >&2
    echo "" >&2
    echo "Arguments:" >&2
    echo "  PIDFILE    Path to jobs.pid file (default: ./logs/jobs.pid)" >&2
    echo "" >&2
    echo "Options:" >&2
    echo "  --status   Show status of jobs without killing" >&2
    echo "  --force    Use SIGKILL instead of SIGTERM" >&2
    exit 1
}

PIDFILE="./logs/jobs.pid"
STATUS_ONLY=0
SIGNAL="TERM"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --status)
            STATUS_ONLY=1
            shift
            ;;
        --force)
            SIGNAL="KILL"
            shift
            ;;
        --help|-h)
            usage
            ;;
        *)
            PIDFILE="$1"
            shift
            ;;
    esac
done

if [[ ! -f "$PIDFILE" ]]; then
    echo "Error: PID file not found: $PIDFILE" >&2
    exit 1
fi

echo "Reading jobs from: $PIDFILE"
echo ""

running=0
finished=0

while read -r pid date; do
    [[ -z "$pid" ]] && continue

    if kill -0 "$pid" 2>/dev/null; then
        running=$((running + 1))
        if (( STATUS_ONLY )); then
            echo "  RUNNING: $date (PID $pid)"
        else
            echo "  Killing: $date (PID $pid)"
            kill -"$SIGNAL" "$pid" 2>/dev/null || true
        fi
    else
        finished=$((finished + 1))
        if (( STATUS_ONLY )); then
            echo "  FINISHED: $date (PID $pid)"
        fi
    fi
done < "$PIDFILE"

echo ""
if (( STATUS_ONLY )); then
    echo "Status: $running running, $finished finished"
else
    if (( running > 0 )); then
        echo "Sent SIG$SIGNAL to $running jobs."
        echo "($finished jobs had already finished)"
    else
        echo "No running jobs found. All $finished jobs had already finished."
    fi
fi
