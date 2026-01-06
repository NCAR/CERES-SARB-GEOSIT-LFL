#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 [--bands sw01,sw02,...|all] [--no-clean] [extra external_mix.py args]" >&2
    echo "Example: $0 --bands sw01,lw01 --start 2010-01-01T00 --end 2010-01-01T00" >&2
    exit 1
}

BANDS=()
CLEAN_AER=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bands)
            IFS=',' read -ra BANDS <<< "$2"
            shift 2
            ;;
        --no-clean)
            CLEAN_AER=0
            shift
            ;;
        --help|-h)
            usage
            ;;
        *)
            break
            ;;
    esac
done

# Remaining args go straight to external_mix.py
# Remaining args go straight to external_mix.py
EXTRA_ARGS=("$@")

# Detect data root for cleanup based on args (very lightweight parsing)
DATADIR="${HOME}/Data"
SUBDIR="GEOSIT"
for ((i=0; i<${#EXTRA_ARGS[@]}; i++)); do
    case "${EXTRA_ARGS[i]}" in
        --ceres)
            DATADIR="/CERES/sarb/dfillmor"
            SUBDIR="GEOSIT_alpha_4"
            ;;
        --datadir)
            # Next arg should be the path
            if (( i + 1 < ${#EXTRA_ARGS[@]} )); then
                DATADIR="${EXTRA_ARGS[i+1]}"
            fi
            ;;
    esac
done

# Default bands: all SW01–SW14 and LW01–LW12
if [[ ${#BANDS[@]} -eq 0 ]]; then
    for i in $(seq 1 14); do BANDS+=("sw$(printf '%02d' "$i")"); done
    for i in $(seq 1 12); do BANDS+=("lw$(printf '%02d' "$i")"); done
fi

if [[ ${#BANDS[@]} -eq 1 && "${BANDS[0]}" == "all" ]]; then
    BANDS=()
    for i in $(seq 1 14); do BANDS+=("sw$(printf '%02d' "$i")"); done
    for i in $(seq 1 12); do BANDS+=("lw$(printf '%02d' "$i")"); done
fi

for BAND in "${BANDS[@]}"; do
    echo "Running external_mix.py for band $BAND"

    if [[ $CLEAN_AER -eq 1 ]]; then
        band_upper=$(echo "$BAND" | tr '[:lower:]' '[:upper:]')
        pattern="${DATADIR}/${SUBDIR}/**/*AER_${band_upper}*.nc4"
        # Expand matches using find (portable, no mapfile)
        to_delete=()
        while IFS= read -r f; do
            to_delete+=("$f")
        done < <(find "${DATADIR}/${SUBDIR}" -type f -name "*AER_${band_upper}*.nc4" 2>/dev/null)
        if (( ${#to_delete[@]} )); then
            echo "Cleaning preexisting AER files for $BAND:"
            for f in "${to_delete[@]}"; do
                echo "  rm $f"
                rm -f "$f"
            done
        fi
    fi

    echo ">>> external_mix.py --band $BAND ${EXTRA_ARGS[*]:-}"
    python external_mix.py --band "$BAND" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
    echo "Finished external_mix.py for band $BAND"
done
