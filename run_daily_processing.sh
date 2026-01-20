#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    echo "Usage: $0 --start YYYY-MM-DD --end YYYY-MM-DD [options]" >&2
    echo "" >&2
    echo "Runs species_optics and external_mix for all bands, one background job per day." >&2
    echo "" >&2
    echo "Required:" >&2
    echo "  --start DATE    Start date (YYYY-MM-DD)" >&2
    echo "  --end DATE      End date (YYYY-MM-DD), inclusive" >&2
    echo "" >&2
    echo "Options:" >&2
    echo "  --logdir DIR    Directory for log files (default: ./logs)" >&2
    echo "  --max-jobs N    Maximum concurrent background jobs (default: unlimited)" >&2
    echo "  --dry-run       Print what would be executed without running" >&2
    echo "  --ceres         Pass --ceres flag to processing scripts" >&2
    echo "  --datadir DIR   Pass --datadir to processing scripts" >&2
    echo "" >&2
    echo "Example:" >&2
    echo "  $0 --start 2010-01-01 --end 2010-01-31 --logdir ./logs --ceres" >&2
    exit 1
}

START_DATE=""
END_DATE=""
LOGDIR="./logs"
MAX_JOBS=0
DRY_RUN=0
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --start)
            START_DATE="$2"
            shift 2
            ;;
        --end)
            END_DATE="$2"
            shift 2
            ;;
        --logdir)
            LOGDIR="$2"
            shift 2
            ;;
        --max-jobs)
            MAX_JOBS="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --ceres)
            EXTRA_ARGS+=(--ceres)
            shift
            ;;
        --datadir)
            EXTRA_ARGS+=(--datadir "$2")
            shift 2
            ;;
        --help|-h)
            usage
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            ;;
    esac
done

if [[ -z "$START_DATE" || -z "$END_DATE" ]]; then
    echo "Error: --start and --end are required" >&2
    usage
fi

# Validate date format
if ! date -j -f "%Y-%m-%d" "$START_DATE" "+%Y-%m-%d" >/dev/null 2>&1; then
    echo "Error: Invalid start date format. Use YYYY-MM-DD" >&2
    exit 1
fi
if ! date -j -f "%Y-%m-%d" "$END_DATE" "+%Y-%m-%d" >/dev/null 2>&1; then
    echo "Error: Invalid end date format. Use YYYY-MM-DD" >&2
    exit 1
fi

# Create log directory
mkdir -p "$LOGDIR"

# Convert dates to seconds for iteration (macOS date syntax)
start_sec=$(date -j -f "%Y-%m-%d" "$START_DATE" "+%s")
end_sec=$(date -j -f "%Y-%m-%d" "$END_DATE" "+%s")

if (( start_sec > end_sec )); then
    echo "Error: Start date must be before or equal to end date" >&2
    exit 1
fi

# Track background jobs
declare -a PIDS=()
declare -a JOB_DATES=()

wait_for_slot() {
    if (( MAX_JOBS > 0 && ${#PIDS[@]} >= MAX_JOBS )); then
        # Wait for at least one job to finish
        wait -n 2>/dev/null || true
        # Clean up finished jobs
        local new_pids=()
        local new_dates=()
        for i in "${!PIDS[@]}"; do
            if kill -0 "${PIDS[i]}" 2>/dev/null; then
                new_pids+=("${PIDS[i]}")
                new_dates+=("${JOB_DATES[i]}")
            fi
        done
        PIDS=("${new_pids[@]}")
        JOB_DATES=("${new_dates[@]}")
    fi
}

# Function to run a single day's processing
run_day() {
    local day_date="$1"
    local day_start="${day_date}T00"
    local day_end="${day_date}T23"
    local logfile="${LOGDIR}/processing_${day_date}.log"

    # Create a unique temp directory for this day's optics files
    local optics_tmpdir
    optics_tmpdir=$(mktemp -d -t "optics_${day_date}.XXXXXX")

    {
        echo "========================================"
        echo "Processing date: $day_date"
        echo "Started at: $(date)"
        echo "Optics tmpdir: $optics_tmpdir"
        echo "========================================"
        echo ""

        # Run species_optics for all bands
        echo "=== Running species_optics ==="
        "${SCRIPT_DIR}/run_species_optics.sh" \
            --bands all \
            --optics_tmpdir "$optics_tmpdir" \
            --start "$day_start" --end "$day_end" \
            "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"

        echo ""
        echo "=== Running external_mix ==="
        # Run external_mix for all bands
        "${SCRIPT_DIR}/run_external_mix.sh" \
            --bands all \
            --start "$day_start" --end "$day_end" \
            "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"

        echo ""
        echo "========================================"
        echo "Completed date: $day_date"
        echo "Finished at: $(date)"
        echo "========================================"
    } > "$logfile" 2>&1

    local status=$?

    # Clean up temp directory
    rm -rf "$optics_tmpdir"

    return $status
}

echo "Daily Processing Pipeline"
echo "========================="
echo "Start date: $START_DATE"
echo "End date:   $END_DATE"
echo "Log dir:    $LOGDIR"
if (( MAX_JOBS > 0 )); then
    echo "Max jobs:   $MAX_JOBS"
fi
echo ""

# Iterate over each day
current_sec=$start_sec
day_count=0

while (( current_sec <= end_sec )); do
    current_date=$(date -j -f "%s" "$current_sec" "+%Y-%m-%d")
    day_count=$((day_count + 1))

    if (( DRY_RUN )); then
        echo "[DRY RUN] Would launch job for $current_date"
    else
        wait_for_slot

        echo "Launching background job for $current_date (log: ${LOGDIR}/processing_${current_date}.log)"
        run_day "$current_date" &
        PIDS+=($!)
        JOB_DATES+=("$current_date")
    fi

    # Advance to next day (add 86400 seconds)
    current_sec=$((current_sec + 86400))
done

if (( DRY_RUN )); then
    echo ""
    echo "Dry run complete. Would have launched $day_count jobs."
    exit 0
fi

echo ""
echo "Launched $day_count background jobs."
echo "Waiting for all jobs to complete..."

# Wait for all background jobs
failed_jobs=()
for i in "${!PIDS[@]}"; do
    if ! wait "${PIDS[i]}"; then
        failed_jobs+=("${JOB_DATES[i]}")
    fi
done

echo ""
echo "========================================"
echo "All jobs completed."

if (( ${#failed_jobs[@]} > 0 )); then
    echo "FAILED jobs (${#failed_jobs[@]}):"
    for d in "${failed_jobs[@]}"; do
        echo "  - $d (see ${LOGDIR}/processing_${d}.log)"
    done
    exit 1
else
    echo "All $day_count jobs completed successfully."
fi
