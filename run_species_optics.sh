#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 [--bands sw01,sw02,...|all] [extra species_optics.py args]" >&2
    echo "Example: $0 --bands sw01,lw01 --start 2010-01-01T00 --end 2010-01-01T00" >&2
    exit 1
}

BANDS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bands)
            IFS=',' read -ra BANDS <<< "$2"
            shift 2
            ;;
        --help|-h)
            usage
            ;;
        *)
            break
            ;;
    esac
done

# Remaining args go straight to species_optics.py
EXTRA_ARGS=("$@")

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

# Species without size bins (or hard-coded to first bin internally for nitrate)
SPECIES_NO_BIN=(SU OCPHO OCPHI BCPHO BCPHI NI)
# Species that require explicit size bins
SPECIES_WITH_BIN=(SS DU)
SIZE_BINS=(001 002 003 004 005)

for BAND in "${BANDS[@]}"; do
    echo "Running species_optics.py for band $BAND"

    for SP in "${SPECIES_NO_BIN[@]}"; do
        echo ">>> species_optics.py --species $SP --band $BAND ${EXTRA_ARGS[*]}"
        python species_optics.py --species "$SP" --band "$BAND" "${EXTRA_ARGS[@]}"
    done

    for SP in "${SPECIES_WITH_BIN[@]}"; do
        for BIN in "${SIZE_BINS[@]}"; do
            echo ">>> species_optics.py --species $SP --size_bin $BIN --band $BAND ${EXTRA_ARGS[*]}"
            python species_optics.py --species "$SP" --size_bin "$BIN" --band "$BAND" "${EXTRA_ARGS[@]}"
        done
    done

    echo "All species processed for band $BAND"
done
