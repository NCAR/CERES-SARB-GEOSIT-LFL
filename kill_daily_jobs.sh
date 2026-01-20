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
    echo "  --all      Also kill any orphaned species_optics/external_mix processes" >&2
    exit 1
}

PIDFILE="./logs/jobs.pid"
STATUS_ONLY=0
SIGNAL="TERM"
KILL_ALL=0

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
        --all)
            KILL_ALL=1
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

# Recursively get all descendant PIDs of a process
get_descendants() {
    local parent=$1
    local children
    children=$(pgrep -P "$parent" 2>/dev/null) || true
    for child in $children; do
        echo "$child"
        get_descendants "$child"
    done
}

# Kill a process and all its descendants (children first, then parent)
kill_tree() {
    local pid=$1
    local sig=$2
    local descendants
    descendants=$(get_descendants "$pid")

    # Kill children first (deepest first would be ideal, but this works)
    for desc in $descendants; do
        if kill -0 "$desc" 2>/dev/null; then
            kill -"$sig" "$desc" 2>/dev/null || true
        fi
    done

    # Then kill the parent
    if kill -0 "$pid" 2>/dev/null; then
        kill -"$sig" "$pid" 2>/dev/null || true
    fi
}

# Count descendants of a process
count_descendants() {
    local pid=$1
    get_descendants "$pid" | wc -l | tr -d ' '
}

if [[ ! -f "$PIDFILE" ]]; then
    echo "Error: PID file not found: $PIDFILE" >&2
    exit 1
fi

echo "Reading jobs from: $PIDFILE"
echo ""

running=0
finished=0
total_children=0

while read -r pid date; do
    [[ -z "$pid" ]] && continue

    if kill -0 "$pid" 2>/dev/null; then
        running=$((running + 1))
        num_children=$(count_descendants "$pid")
        total_children=$((total_children + num_children))
        if (( STATUS_ONLY )); then
            echo "  RUNNING: $date (PID $pid, $num_children child processes)"
        else
            echo "  Killing: $date (PID $pid + $num_children children)"
            kill_tree "$pid" "$SIGNAL"
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
    if (( running > 0 )); then
        echo "         $total_children total child processes"
    fi
else
    if (( running > 0 )); then
        echo "Sent SIG$SIGNAL to $running jobs + $total_children child processes."
        echo "($finished jobs had already finished)"
    else
        echo "No running jobs found. All $finished jobs had already finished."
    fi
fi

# Optionally kill any orphaned processing scripts
if (( KILL_ALL )) && (( ! STATUS_ONLY )); then
    echo ""
    echo "Checking for orphaned processes..."

    orphans=$(pgrep -f "(species_optics|external_mix)\.py" 2>/dev/null) || true
    if [[ -n "$orphans" ]]; then
        orphan_count=$(echo "$orphans" | wc -l | tr -d ' ')
        echo "Found $orphan_count orphaned process(es):"
        for opid in $orphans; do
            cmdline=$(ps -p "$opid" -o args= 2>/dev/null | head -c 80) || cmdline="(unknown)"
            echo "  Killing PID $opid: $cmdline"
            kill -"$SIGNAL" "$opid" 2>/dev/null || true
        done
    else
        echo "No orphaned processes found."
    fi
elif (( STATUS_ONLY )); then
    echo ""
    echo "Checking for orphaned processes..."
    orphans=$(pgrep -f "(species_optics|external_mix)\.py" 2>/dev/null) || true
    if [[ -n "$orphans" ]]; then
        orphan_count=$(echo "$orphans" | wc -l | tr -d ' ')
        echo "Found $orphan_count orphaned process(es):"
        for opid in $orphans; do
            cmdline=$(ps -p "$opid" -o args= 2>/dev/null | head -c 80) || cmdline="(unknown)"
            echo "  PID $opid: $cmdline"
        done
        echo ""
        echo "Use --all to kill orphaned processes"
    else
        echo "No orphaned processes found."
    fi
fi
