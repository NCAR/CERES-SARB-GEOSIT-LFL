# check_aer_grid: date-range averaging window — design

Date: 2026-05-01

## Purpose

Extend `check_aer_grid.py` so the time-averaging window can span more than
one day. The existing single-day mode keeps working unchanged.

The script produces, per band:

- A 9×18 area-weighted regional-mean map text report (today's output, with
  one new line in the header for ranges).
- A NetCDF file containing the full-resolution 180×288 mean field of
  `Extinction_Column_Optical_Depth` over the window. **New output.**

## Scope

- `check_aer_grid.py` only. No other script changes.
- No callers in the repo (the script is invoked by hand), so no shell or
  pipeline updates are required.

## Invocation

Existing single-day form keeps working byte-for-byte:

```
./check_aer_grid.py --date 2008-07-01 --bands sw01 --ceres
```

New range form:

```
./check_aer_grid.py --date-begin 2008-07-01 --date-end 2008-07-31 \
    --bands sw01,sw02 --ceres
```

Validation, all enforced at the CLI boundary via `parser.error(...)`:

- `--date` is mutually exclusive with `--date-begin`/`--date-end`.
- `--date-begin` and `--date-end` must appear together; passing only one
  is an error.
- `end >= begin`. `begin == end` is allowed and treated as a single-day
  invocation everywhere it shows up: report uses the single-day header
  format, text file is `aer_check_{BAND}_{date}.txt`, NetCDF is
  `aer_mean_{BAND}_{date}.nc`. The only externally visible difference vs
  `--date <date>` is the CLI flags the user typed.
- All dates parsed with `datetime.date.fromisoformat`.

`--bands`, `--datadir`, `--outdir`, `--ceres`, `--color`/`--no-color` are
unchanged.

## Internals

New helper:

```python
def iter_dates(begin, end):
    """Yield 'YYYY-MM-DD' strings for begin..end inclusive."""
```

`build_paths(datadir, ceres, date, band)` is unchanged.

The existing `load_daily_mean(paths)` is replaced by a window-aware
loader that operates over a list of dates:

```python
def load_window_mean(datadir, ceres, dates, band):
    """Average Extinction_Column_Optical_Depth over all available
    timesteps in the window.

    Returns:
        field:                (180, 288) float64, np.nanmean over the
                              full stack of available timestep arrays.
        lat, lon:             1-D arrays from the first file read.
        n_timesteps_found:    int, number of timestep files actually
                              loaded.
        n_timesteps_total:    int, 8 * len(dates).
        n_days_with_data:     int, number of dates that contributed at
                              least one timestep.
        n_days_total:         int, len(dates).
    """
```

Implementation:

- For each date in `dates`, build the 8 paths via `build_paths`.
- For each path that exists, open with `xr.open_dataset`, append the
  field array, capture lat/lon from the first opened file.
- Track per-date timestep counts so `n_days_with_data` can be computed.
- Single `np.nanmean(np.stack(fields), axis=0)` over the full stack.
  Every available timestep contributes equally — Approach 1 from
  brainstorming. A day with 6/8 timesteps contributes 6 fields; a full
  day contributes 8.
- If the lat/lon arrays from a later file differ in shape from the
  first, log ERROR and abort that band.

Memory: 31 days × 8 timesteps × 180×288 × 8 bytes ≈ 102 MB. Acceptable.

`aggregate_cells(field, lat)` is unchanged.

`main()` always calls `load_window_mean` with a `dates` list, even for
the single-day case (`dates=[args.date]`). One code path.

## Report header

Single-day report (when invoked with `--date` or with `begin == end`):
unchanged from today, byte-identical.

```
AER SW01 daily-mean Extinction_Column_Optical_Depth
date:        2008-07-01
source:      /CERES/.../AER_SW01.20080701T*.V01.nc4
timesteps:   8/8
global mean: 0.18  (area-weighted, cos lat)
...
```

Range report (when invoked with `--date-begin`/`--date-end` and
`begin != end`):

```
AER SW01 window-mean Extinction_Column_Optical_Depth
range:       2008-07-01 to 2008-07-31  (31 days)
source:      /CERES/.../AER_SW01.??????????T*.V01.nc4
timesteps:   246/248
days:        31/31
global mean: 0.18  (area-weighted, cos lat)
global min:  0.00
global max:  4.21
NaN cells:   0
NaN points:  0 / 51840
```

Differences vs single-day:

- Title says `window-mean` instead of `daily-mean`.
- `date:` line replaced by `range:` line that names both endpoints and
  the day count.
- New `days: D/T` line where D is days that contributed ≥1 timestep and
  T is total days requested.
- `source:` glob replaces the 8 date digits with `?` so the pattern
  matches all dates in the window.
- All other lines unchanged in format.

## Outputs

Per band, per invocation:

| invocation | text report | NetCDF mean |
|---|---|---|
| `--date 2008-07-01` | `qc/aer_check_SW01_2008-07-01.txt` | `qc/aer_mean_SW01_2008-07-01.nc` |
| `--date-begin 2008-07-01 --date-end 2008-07-31` | `qc/aer_check_SW01_2008-07-01_to_2008-07-31.txt` | `qc/aer_mean_SW01_2008-07-01_to_2008-07-31.nc` |

The text report keeps the `aer_check_` prefix to preserve the existing
single-day filename. The NetCDF uses a distinct `aer_mean_` prefix so
the filename advertises that the contents are a time-mean field rather
than a QC report.

NetCDF is always written, including for single-day calls. The script
exits 0 unless a band produced 0 timesteps (see Exit code below).

The README "Quick QC" section is updated to show the new range form
and to mention the `aer_mean_*.nc` output.

## NetCDF contents

Format: NETCDF4_CLASSIC via `xarray.Dataset.to_netcdf`.

Dimensions:

- `lat` (180), `lon` (288). No time dimension — the field has been
  averaged over time.

Variables:

- `Extinction_Column_Optical_Depth(lat, lon)`, float64. Variable name
  matches the source so downstream code can reuse the same key.
  Attributes:
  - `cell_methods = "time: mean"`
  - `long_name = "Extinction Column Optical Depth (time mean)"`
- `lat(lat)`, `lon(lon)` — copied from the first input file read,
  preserving the source's `units` and any other attrs xarray carries
  through.

Global attributes:

- `time_coverage_start = "<begin>T00:00:00Z"`
- `time_coverage_end   = "<end>T21:00:00Z"` (last timestep of the last
  day; T21 is the latest 3-hourly file)
- `n_timesteps_used`, `n_timesteps_expected` — integers
- `n_days_with_data`, `n_days_total` — integers
- `band` — e.g. `"SW01"`
- `source` — the same glob string shown in the text report
- `history = "Created by check_aer_grid.py on <iso utc>"`

For single-day calls, `time_coverage_start`/`end` use the same date for
both, with `T00:00:00Z`/`T21:00:00Z`.

## Exit code

Per band, exit 1 only if **0 timesteps** were found across the entire
window. Partial days and missing individual timesteps emit WARNING and
the band continues.

`any_failed = True` if any requested band produced 0 timesteps. Final
exit is `1` if `any_failed`, else `0`. Identical semantics to today,
just generalized to the window.

## Errors and edge cases

- Invalid date format → `parser.error(...)` (CLI boundary).
- `--date` together with `--date-begin`/`--date-end` → `parser.error`.
- Only one of `--date-begin`/`--date-end` → `parser.error`.
- `end < begin` → `parser.error`.
- A band with 0 timesteps in the window → ERROR log, no `.txt` or `.nc`
  written for that band, `any_failed = True`.
- Lat/lon shape mismatch between days within a band → ERROR log, skip
  that band, `any_failed = True`.

## Testing

Manual smoke tests (run from the repo root):

1. Single-day backward compatibility:
   ```
   ./check_aer_grid.py --date 2008-07-01 --bands sw01 --ceres \
       --outdir /tmp/qc_new
   diff qc/aer_check_SW01_2008-07-01.txt \
        /tmp/qc_new/aer_check_SW01_2008-07-01.txt
   ```
   Must be byte-identical (no diff output).

2. Single-day NetCDF round-trip:
   ```
   python -c "import xarray as xr, numpy as np; \
       ds = xr.open_dataset('/tmp/qc_new/aer_mean_SW01_2008-07-01.nc'); \
       w = np.cos(np.deg2rad(ds.lat.values)); \
       f = ds['Extinction_Column_Optical_Depth'].values; \
       print((f * w[:,None]).sum() / (w[:,None] * np.isfinite(f)).sum())"
   ```
   Should match the `global mean` line in the text report to 2 decimals.

3. Range run:
   ```
   ./check_aer_grid.py --date-begin 2008-07-01 --date-end 2008-07-31 \
       --bands sw01 --ceres --outdir /tmp/qc_range
   ```
   Inspect `/tmp/qc_range/aer_check_SW01_2008-07-01_to_2008-07-31.txt`
   for the new header format. Verify
   `aer_mean_SW01_2008-07-01_to_2008-07-31.nc` exists and `ncdump -h`
   shows the expected dims, vars, and global attrs.

4. CLI validation (each must `parser.error` with exit 2):
   ```
   ./check_aer_grid.py --date 2008-07-01 --date-begin 2008-07-01 \
       --date-end 2008-07-02 --bands sw01
   ./check_aer_grid.py --date-begin 2008-07-01 --bands sw01
   ./check_aer_grid.py --date-begin 2008-07-31 \
       --date-end 2008-07-01 --bands sw01
   ```

Unit-test additions are out of scope; the script has no test suite
today and adding one is a separate change.

## Out of scope

- Changes to other plot/QC scripts.
- A test suite for `check_aer_grid.py`.
- Equal-day weighting (Approach 2 from brainstorming) — not the chosen
  semantics.
- Streaming reduction (Approach 3) — not needed at this memory scale.
- Any change to source-data layout, the 9×18 cell aggregation math, or
  the colorized stdout output.
