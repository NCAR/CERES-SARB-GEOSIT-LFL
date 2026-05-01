# AER per-band grid checker — design

Date: 2026-05-01

## Purpose

Per-band, text-only sanity check of `AER_{band}` daily output. Produces one
file per (band, date) containing a 9×18 area-weighted regional-mean map of
column AOD plus global stats. Operates on whichever bands have completed —
intended to be run while a production run is still in progress.

Complements existing diagnostics:

- `validate_run.py` — file presence / non-zero size only.
- `plot_species_validation.py` — per-species comparison vs native GEOS-IT,
  produces plots.

This script fills the gap: a fast, plot-free, per-band value check that
operates on the AER aggregate and prints a readable map.

## Invocation

```
./check_aer_grid.py --date 2008-07-01 --bands sw01,sw02 --ceres
./check_aer_grid.py --date 2008-07-01 --bands sw01 --datadir $HOME/Data --outdir qc
```

Flags mirror `plot_species_validation.py`:

- `--date YYYY-MM-DD` (required)
- `--bands` comma-separated list, e.g. `sw01,sw02,lw03` (required)
- `--datadir DIR` default `$HOME/Data`
- `--outdir DIR` default `qc` (created on demand)
- `--ceres` use CERES production paths (`/CERES/sarb/dfillmor/GEOSIT_alpha_4/`)

LW bands work with no special-casing (same file pattern).

## What it does, per band

1. Open the 8 timestep files
   `AER_{BAND}.{date}T{HH}00.V01.nc4` for `HH ∈ {00,03,06,09,12,15,18,21}`.
   Missing timesteps are logged at WARNING level; the script continues with
   what is present.
2. Stack `Extinction_Column_Optical_Depth` over time and take the mean over
   the time axis to produce the daily mean field on the 288×180 subsampled
   grid. Use `nanmean` so a single bad value does not poison a cell.
3. Reshape into 9 × 18 cells (each 20 lat points × 16 lon points = 320
   points). Compute each cell's mean weighted by cos(lat). Compute the
   global mean the same way.
4. Write `{outdir}/aer_check_{BAND}_{date}.txt`.

## File format

Roughly 95 columns wide, fixed width.

```
AER {BAND} daily-mean Extinction_Column_Optical_Depth
date:        2008-07-01
source:      /CERES/.../AER_SW01.2008-07-01T*.V01.nc4
timesteps:   8/8
global mean: 0.15  (area-weighted, cos lat)
global min:  0.00
global max:  3.25
NaN cells:   0
NaN points:  0 / 51840

      170W  150W  130W  110W   90W   70W   50W   30W   10W   10E   30E   50E   70E   90E  110E  130E  150E  170E
 80N   0.12  0.13  ...
 60N   ...
  ...
 80S   ...
```

- Cell value format: `%5.2f` (5 chars). No explicit separator — the
  format's leading space provides spacing. Range covered: 0.00 through
  99.99. AOD will not exceed that in practice.
- Lat label: 4 chars (`" 80N"`, `"  0 "`, `" 80S"`) followed by one space.
- Lon header row aligned with cell centers (`170W`, `150W`, …, `170E`).
- All-NaN cell prints `"  NaN"` (5 chars, same width as values).
- Global mean / min / max printed with two decimals to match cell format.

## Cell geometry

The 288×180 subsampled grid (lon × lat), produced by `species_optics.py`
subsampling, has lat from -90 to +90 (180 points, 1° spacing) and lon from
-180 to ~180 (288 points, 1.25° spacing).

- 9 lat bands × 20 points each = 180.
- 18 lon bands × 16 points each = 288.

Cell `(i, j)` (with `i` running south→north or north→south depending on the
file lat order) covers lat points `[20*i : 20*(i+1)]` and lon points
`[16*j : 16*(j+1)]`. Cell-center lat labels are at `±80, ±60, ±40, ±20, 0`.
Cell-center lon labels are at `±10, ±30, ±50, ..., ±170`.

The script reads the lat array from the file rather than assuming an order;
the output map always prints north-to-south (top row 80N, bottom row 80S)
regardless of the file's storage order.

## Area weighting

For both cell means and the global mean, weights are `cos(lat)` evaluated at
each native subsampled-grid latitude (not the cell center). NaN points are
excluded from both numerator and denominator.

This matches the convention used in `validation_20080701.md` (area-weighted
column AOD).

## Behavior on missing files

- 0 of 8 timesteps present → log error, exit 1 for that band, no file
  written. Other bands in the same invocation continue.
- 1–7 of 8 present → file is written; `timesteps:` line shows `N/8`; the
  daily mean is computed over what is present.
- 8 of 8 present → normal.

Per-band exit handling: the script processes each requested band
independently and exits 0 if every band produced a file, 1 if any band
had zero timesteps available.

## Out of scope

- Plots. (`plot_species_validation.py` already covers that.)
- Per-species checks. Per-species data is wiped after external mix in the
  current production run, so there is nothing to check. The AER aggregate
  is the only check target.
- Comparison to a reference run or pass/fail thresholds. This is an
  eyeball check — the user reads the map and the global stats.
- Pipeline integration. Script is standalone for now; can be wired into
  `run_daily_processing.sh` in a follow-up if desired.

## Testing

Manual verification on the in-progress production run:

1. Run against SW01 and SW02 for 2008-07-01 (which have output already).
2. Confirm the global mean falls in the same ballpark as the
   `validation_20080701.md` total AOD figure (~0.15 at 550 nm — SW01/SW02
   are different bands, so values will differ, but should be sane and
   non-NaN).
3. Confirm map orientation: NH summer (July 1) should show heavier AOD
   in the NH mid-latitudes (Saharan dust, biomass burning) than the SH.
4. Run with one timestep file deliberately absent to confirm the
   `timesteps: 7/8` path works.
