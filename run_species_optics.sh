#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 [--bands sw01,sw02,...|all] [--optics_tmpdir DIR|auto] [extra species_optics.py args]" >&2
    echo "Example: $0 --bands sw01,lw01 --optics_tmpdir auto --start 2010-01-01T00 --end 2010-01-01T00" >&2
    echo "" >&2
    echo "  --optics_tmpdir DIR   Use DIR for local optics file copies (avoids file locking)" >&2
    echo "  --optics_tmpdir auto  Auto-create a temp directory (cleaned up on exit)" >&2
    exit 1
}

BANDS=()
OPTICS_TMPDIR=""
AUTO_TMPDIR=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bands)
            IFS=',' read -ra BANDS <<< "$2"
            shift 2
            ;;
        --optics_tmpdir)
            if [[ "$2" == "auto" ]]; then
                AUTO_TMPDIR=1
            else
                OPTICS_TMPDIR="$2"
            fi
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

# Create auto tmpdir if requested
if [[ $AUTO_TMPDIR -eq 1 ]]; then
    OPTICS_TMPDIR=$(mktemp -d -t optics_tmp.XXXXXX)
    echo "Created temp directory for optics: $OPTICS_TMPDIR"
    # Clean up on exit
    trap 'echo "Cleaning up $OPTICS_TMPDIR"; rm -rf "$OPTICS_TMPDIR"' EXIT
fi

# Build tmpdir argument for Python script
TMPDIR_ARG=()
if [[ -n "$OPTICS_TMPDIR" ]]; then
    mkdir -p "$OPTICS_TMPDIR"
    TMPDIR_ARG=(--optics_tmpdir "$OPTICS_TMPDIR")
    echo "Using optics temp directory: $OPTICS_TMPDIR"
fi

# Species without size bins
SPECIES_NO_BIN=(OCPHO OCPHI BCPHO BCPHI)
# Species that require explicit size bins
SPECIES_5BIN=(SS DU)
SPECIES_3BIN=(NI)
SPECIES_2BIN=(SU)
SIZE_BINS_5=(001 002 003 004 005)
SIZE_BINS_3=(001 002 003)
SIZE_BINS_2=(001 002)

for BAND in "${BANDS[@]}"; do
    echo "Running species_optics.py for band $BAND"

    for SP in "${SPECIES_NO_BIN[@]}"; do
        echo ">>> species_optics.py --species $SP --band $BAND ${TMPDIR_ARG[*]:-} ${EXTRA_ARGS[*]:-}"
        python species_optics.py --species "$SP" --band "$BAND" "${TMPDIR_ARG[@]+"${TMPDIR_ARG[@]}"}" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
    done

    for SP in "${SPECIES_5BIN[@]}"; do
        for BIN in "${SIZE_BINS_5[@]}"; do
            echo ">>> species_optics.py --species $SP --size_bin $BIN --band $BAND ${TMPDIR_ARG[*]:-} ${EXTRA_ARGS[*]:-}"
            python species_optics.py --species "$SP" --size_bin "$BIN" --band "$BAND" "${TMPDIR_ARG[@]+"${TMPDIR_ARG[@]}"}" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
        done
    done

    for SP in "${SPECIES_3BIN[@]}"; do
        for BIN in "${SIZE_BINS_3[@]}"; do
            echo ">>> species_optics.py --species $SP --size_bin $BIN --band $BAND ${TMPDIR_ARG[*]:-} ${EXTRA_ARGS[*]:-}"
            python species_optics.py --species "$SP" --size_bin "$BIN" --band "$BAND" "${TMPDIR_ARG[@]+"${TMPDIR_ARG[@]}"}" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
        done
    done

    for SP in "${SPECIES_2BIN[@]}"; do
        for BIN in "${SIZE_BINS_2[@]}"; do
            echo ">>> species_optics.py --species $SP --size_bin $BIN --band $BAND ${TMPDIR_ARG[*]:-} ${EXTRA_ARGS[*]:-}"
            python species_optics.py --species "$SP" --size_bin "$BIN" --band "$BAND" "${TMPDIR_ARG[@]+"${TMPDIR_ARG[@]}"}" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
        done
    done

    echo "All species processed for band $BAND"
done
