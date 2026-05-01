# check_aer_grid: date-range averaging window — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--date-begin`/`--date-end` averaging-window option to `check_aer_grid.py`, plus a per-band NetCDF mean-field output. Existing `--date` invocations remain byte-identical.

**Architecture:** Pure additive edit to one script (`check_aer_grid.py`). Today's `load_daily_mean` is generalized to `load_window_mean` operating over a list of dates (Approach 1 from the spec: a single `np.nanmean` over all available timestep arrays in the window). `main()` always builds a `dates` list — single-day case is `dates=[args.date]`. New helpers add CLI validation, range-aware filenames, range-aware report header, and a NetCDF writer using `xarray.Dataset.to_netcdf`. README "Quick QC" gets a range example and a note about the `.nc` output.

**Tech Stack:** Python 3, numpy, xarray, netCDF4 (already available in the `sarb` conda env that users activate). No new dependencies. argparse + logging unchanged.

**Spec:** `docs/superpowers/specs/2026-05-01-ascii-map-date-range-design.md`

**Testing approach:** This project has no existing test framework (no `tests/`, no pytest config, sibling scripts have no tests). The approved spec specifies manual verification. Each task ends with a concrete verification step — REPL-style sanity checks for arithmetic-heavy edits, real-data invocations for integration. The strongest regression net is **byte-identical text output for single-day `--date` calls**: the `qc/aer_check_SW01_2008-07-01.txt` already in the repo is the golden reference, diffed at the end of every task that touches loading, filenames, or report formatting.

**Reference data:** July 2008 daily runs are complete (data under `/CERES/sarb/dfillmor/GEOSIT_alpha_4/2008/07/`). Use `--date 2008-07-01 --bands sw01 --ceres` for single-day verification and `--date-begin 2008-07-01 --date-end 2008-07-03 --bands sw01 --ceres` for short-range integration.

---

### Task 1: Add `iter_dates` helper

A tiny utility used by every later task. Inclusive on both endpoints. Lives at module scope above `build_paths`.

**Files:**
- Modify: `check_aer_grid.py` — add helper near top of module (after `TIMESTEPS` constant, before `build_paths`).

- [ ] **Step 1: Add the helper**

Insert after the `TIMESTEPS = [...]` block (around line 21):

```python
def iter_dates(begin, end):
    """Yield 'YYYY-MM-DD' strings for begin..end inclusive.

    begin, end: datetime.date instances. end >= begin.
    """
    n = (end - begin).days + 1
    for i in range(n):
        yield (begin + datetime.timedelta(days=i)).isoformat()
```

- [ ] **Step 2: REPL sanity check**

Run:
```
python -c "
import datetime
from check_aer_grid import iter_dates
b = datetime.date(2008, 7, 1)
e = datetime.date(2008, 7, 3)
print(list(iter_dates(b, e)))
print(list(iter_dates(b, b)))
"
```

Expected:
```
['2008-07-01', '2008-07-02', '2008-07-03']
['2008-07-01']
```

- [ ] **Step 3: Commit**

```bash
git add check_aer_grid.py
git commit -m "check_aer_grid: add iter_dates helper for date windows"
```

---

### Task 2: Replace `load_daily_mean` with `load_window_mean`

Generalize the loader to operate over a list of dates and report richer counts. The existing `aggregate_cells` and report-formatting code are untouched. `main()` is updated to call the new function for the single-day case (`dates=[args.date]`) — no externally visible behavior change yet.

**Files:**
- Modify: `check_aer_grid.py` — replace `load_daily_mean` (lines 47-72) and update its call site in `main()` (around line 236).

- [ ] **Step 1: Replace the loader**

Replace the entire `load_daily_mean` function with:

```python
def load_window_mean(datadir, ceres, dates, band):
    """Average Extinction_Column_Optical_Depth over all available
    timesteps in the window.

    dates: list of 'YYYY-MM-DD' strings, in any order.
    band:  uppercase, e.g. 'SW01'.

    Returns:
        field:               (180, 288) float64, np.nanmean over the
                             full stack of available timestep arrays,
                             or None if zero timesteps were found.
        lat, lon:            1-D arrays from the first file read, or
                             None if zero timesteps were found.
        n_timesteps_found:   int, number of timestep files actually
                             loaded across all dates.
        n_timesteps_total:   int, 8 * len(dates).
        n_days_with_data:    int, number of dates that contributed at
                             least one timestep.
        n_days_total:        int, len(dates).
    """
    fields = []
    lat = lon = None
    n_days_with_data = 0
    for date in dates:
        paths = build_paths(datadir, ceres, date, band)
        day_count = 0
        for p in paths:
            if not os.path.exists(p):
                logging.warning('Missing timestep: %s', p)
                continue
            with xr.open_dataset(p) as ds:
                arr = ds['Extinction_Column_Optical_Depth'].values
                # File stores either (time, lat, lon) with time=1 or (lat, lon).
                if arr.ndim == 3:
                    arr = arr[0]
                if lat is None:
                    lat = ds['lat'].values.astype(np.float64)
                    lon = ds['lon'].values.astype(np.float64)
                else:
                    cur_lat = ds['lat'].values
                    if cur_lat.shape != lat.shape:
                        logging.error(
                            'lat shape mismatch in %s: %s vs %s; '
                            'aborting band',
                            p, cur_lat.shape, lat.shape)
                        return None, None, None, 0, 8 * len(dates), 0, len(dates)
                fields.append(arr.astype(np.float64))
                day_count += 1
        if day_count > 0:
            n_days_with_data += 1
    n_total = 8 * len(dates)
    if not fields:
        return None, None, None, 0, n_total, 0, len(dates)
    field = np.nanmean(np.stack(fields), axis=0)
    return field, lat, lon, len(fields), n_total, n_days_with_data, len(dates)
```

- [ ] **Step 2: Update the call site in `main()`**

Find this block (around line 234-244):

```python
    any_failed = False
    for band in bands:
        paths = build_paths(args.datadir, args.ceres, args.date, band)
        field, lat, lon, n_found = load_daily_mean(paths)
        if n_found == 0:
            logging.error('No timestep files found for %s %s', band, args.date)
            any_failed = True
            continue
        stats = aggregate_cells(field, lat)
        # Use a glob-style source string so the report shows the pattern
        # rather than 8 individual paths.
        source_glob = paths[0].replace('T0000.V01.nc4', 'T*.V01.nc4')
```

Replace with:

```python
    dates = [args.date]                         # placeholder; Task 3 derives this from the new CLI flags
    any_failed = False
    for band in bands:
        field, lat, lon, n_found, n_total, n_days_data, n_days_total = (
            load_window_mean(args.datadir, args.ceres, dates, band))
        if n_found == 0:
            logging.error('No timestep files found for %s in window', band)
            any_failed = True
            continue
        stats = aggregate_cells(field, lat)
        # Use a glob-style source string so the report shows the pattern
        # rather than every individual path.
        first_paths = build_paths(args.datadir, args.ceres, dates[0], band)
        source_glob = first_paths[0].replace('T0000.V01.nc4', 'T*.V01.nc4')
```

(`n_total`, `n_days_data`, `n_days_total` are bound here so later tasks can use them; nothing else changes yet.)

- [ ] **Step 3: Verify single-day text report is byte-identical**

Run:
```
mkdir -p /tmp/qc_t2
./check_aer_grid.py --date 2008-07-01 --bands sw01 --ceres \
    --outdir /tmp/qc_t2 --no-color
diff qc/aer_check_SW01_2008-07-01.txt \
     /tmp/qc_t2/aer_check_SW01_2008-07-01.txt
```

Expected: no diff output. Exit code 0.

- [ ] **Step 4: Commit**

```bash
git add check_aer_grid.py
git commit -m "check_aer_grid: replace load_daily_mean with window-aware loader"
```

---

### Task 3: Add `--date-begin` / `--date-end` CLI flags with validation

Wire the new flags into `argparse`, enforce the validation rules from the spec, and have `main()` build the `dates` list from whichever mode the user invoked. Report header and filenames are still single-day style at this point — Tasks 5 and 6 add the range-aware variants.

**Files:**
- Modify: `check_aer_grid.py` — `main()` argparse section (around lines 195-221) and the `dates = [args.date]` line introduced in Task 2.

- [ ] **Step 1: Make `--date` no longer required, add the new flags**

Replace this block in `main()`:

```python
    parser.add_argument('--date', type=str, required=True,
                        help='date YYYY-MM-DD')
```

with:

```python
    parser.add_argument('--date', type=str, default=None,
                        help='single date YYYY-MM-DD '
                             '(mutually exclusive with --date-begin/--date-end)')
    parser.add_argument('--date-begin', dest='date_begin', type=str,
                        default=None,
                        help='inclusive start date YYYY-MM-DD '
                             '(use with --date-end for a range)')
    parser.add_argument('--date-end', dest='date_end', type=str,
                        default=None,
                        help='inclusive end date YYYY-MM-DD '
                             '(use with --date-begin for a range)')
```

- [ ] **Step 2: Replace the existing `--date` validation with full mode validation**

Find:

```python
    try:
        datetime.date.fromisoformat(args.date)
    except ValueError:
        parser.error(f"--date must be YYYY-MM-DD, got {args.date!r}")
```

Replace with:

```python
    using_single = args.date is not None
    using_range = (args.date_begin is not None) or (args.date_end is not None)
    if using_single and using_range:
        parser.error(
            '--date is mutually exclusive with --date-begin/--date-end')
    if not using_single and not using_range:
        parser.error('one of --date or --date-begin/--date-end is required')
    if using_range and (args.date_begin is None or args.date_end is None):
        parser.error('--date-begin and --date-end must be given together')

    if using_single:
        try:
            d = datetime.date.fromisoformat(args.date)
        except ValueError:
            parser.error(f"--date must be YYYY-MM-DD, got {args.date!r}")
        date_begin = date_end = d
    else:
        try:
            date_begin = datetime.date.fromisoformat(args.date_begin)
        except ValueError:
            parser.error(
                f"--date-begin must be YYYY-MM-DD, got {args.date_begin!r}")
        try:
            date_end = datetime.date.fromisoformat(args.date_end)
        except ValueError:
            parser.error(
                f"--date-end must be YYYY-MM-DD, got {args.date_end!r}")
        if date_end < date_begin:
            parser.error(
                f"--date-end ({date_end}) must be >= --date-begin "
                f"({date_begin})")

    dates = list(iter_dates(date_begin, date_end))
    is_single_day = (date_begin == date_end)
```

- [ ] **Step 3: Remove the now-stale `dates = [args.date]` line**

Delete the placeholder line added in Task 2:

```python
    dates = [args.date]                         # placeholder; Task 3 derives this from the new CLI flags
```

(It's now superseded by `dates = list(iter_dates(date_begin, date_end))` from Step 2.)

- [ ] **Step 4: Verify each invalid combo errors**

Each command must exit non-zero with a `parser.error`-style message on stderr:

```
./check_aer_grid.py --bands sw01
./check_aer_grid.py --date 2008-07-01 --date-begin 2008-07-01 --date-end 2008-07-02 --bands sw01
./check_aer_grid.py --date-begin 2008-07-01 --bands sw01
./check_aer_grid.py --date-end 2008-07-01 --bands sw01
./check_aer_grid.py --date-begin 2008-07-31 --date-end 2008-07-01 --bands sw01
./check_aer_grid.py --date 2008-7-1 --bands sw01
```

Expected for each: prints "usage: ..." and an error explaining the violation, exits with status 2 (argparse default).

Run:
```
./check_aer_grid.py --bands sw01; echo "exit=$?"
```

Expected exit: `exit=2`.

- [ ] **Step 5: Verify the byte-identical single-day report still holds**

Run:
```
rm -rf /tmp/qc_t3 && mkdir -p /tmp/qc_t3
./check_aer_grid.py --date 2008-07-01 --bands sw01 --ceres \
    --outdir /tmp/qc_t3 --no-color
diff qc/aer_check_SW01_2008-07-01.txt \
     /tmp/qc_t3/aer_check_SW01_2008-07-01.txt
```

Expected: no diff output.

- [ ] **Step 6: Verify a short range loads without crashing**

Run:
```
./check_aer_grid.py --date-begin 2008-07-01 --date-end 2008-07-02 \
    --bands sw01 --ceres --outdir /tmp/qc_t3 --no-color
ls /tmp/qc_t3/
```

Expected: `aer_check_SW01_2008-07-01_to_2008-07-02.txt` is **not** there yet (filename builder lands in Task 5); instead a single-day-named file is overwritten. The run should still complete with exit 0 — we're verifying the loader doesn't crash on a multi-day window.

Confirm via the log lines that `Wrote /tmp/qc_t3/...` appeared with no Python traceback.

- [ ] **Step 7: Commit**

```bash
git add check_aer_grid.py
git commit -m "check_aer_grid: add --date-begin/--date-end CLI with validation"
```

---

### Task 4: Range-aware NetCDF write (single-day mode only for now)

Add the NetCDF writer and wire it into `main()`. To keep this task focused, only the single-day filename and `time_coverage_*` are exercised here — the range branch is added in Task 5 alongside the range-aware text filename.

**Files:**
- Modify: `check_aer_grid.py` — add `write_mean_netcdf` helper above `main()`; add a call from `main()` after the text report is written.

- [ ] **Step 1: Add the writer helper**

Insert above `def main():` (around line 192):

```python
def write_mean_netcdf(out_path, field, lat, lon, band, source_glob,
                      n_used, n_expected, n_days_data, n_days_total,
                      date_begin, date_end):
    """Write the time-mean Extinction_Column_Optical_Depth field.

    out_path:    full path to the .nc file to create.
    field:       (180, 288) float64 array (already a time-mean).
    lat, lon:    1-D coord arrays from the source files.
    band:        uppercase band string, e.g. 'SW01'.
    source_glob: pattern string shown in the text report.
    n_used,
    n_expected:  timestep counts to record as global attrs.
    n_days_data,
    n_days_total: day counts to record as global attrs.
    date_begin,
    date_end:    datetime.date instances; written as ISO strings.
    """
    ds = xr.Dataset(
        data_vars={
            'Extinction_Column_Optical_Depth': (
                ('lat', 'lon'),
                field,
                {
                    'cell_methods': 'time: mean',
                    'long_name':
                        'Extinction Column Optical Depth (time mean)',
                },
            ),
        },
        coords={
            'lat': ('lat', lat, {'units': 'degrees_north'}),
            'lon': ('lon', lon, {'units': 'degrees_east'}),
        },
        attrs={
            'band': band,
            'source': source_glob,
            'time_coverage_start': f'{date_begin.isoformat()}T00:00:00Z',
            'time_coverage_end':   f'{date_end.isoformat()}T21:00:00Z',
            'n_timesteps_used': int(n_used),
            'n_timesteps_expected': int(n_expected),
            'n_days_with_data': int(n_days_data),
            'n_days_total': int(n_days_total),
            'history': (
                'Created by check_aer_grid.py on '
                f'{datetime.datetime.utcnow().isoformat(timespec="seconds")}Z'
            ),
        },
    )
    ds.to_netcdf(out_path, format='NETCDF4_CLASSIC')
```

- [ ] **Step 2: Call the writer from `main()`**

Find the end of the per-band loop body (after the existing colorized stdout write, around line 254):

```python
        if do_color:
            sys.stdout.write(format_report(
                band, args.date, source_glob, n_found, stats, colorize=True))
```

Insert immediately after that block (still inside the `for band in bands:` loop):

```python
        nc_path = os.path.join(
            args.outdir, f'aer_mean_{band}_{args.date}.nc')
        write_mean_netcdf(
            nc_path, field, lat, lon, band, source_glob,
            n_found, n_total, n_days_data, n_days_total,
            date_begin, date_end)
        logging.info('Wrote %s', nc_path)
```

(The colorized-stdout block still references `args.date` — leave that for now; Task 6 replaces it with a date-or-range string.)

- [ ] **Step 3: Verify single-day NetCDF round-trips**

Run:
```
rm -rf /tmp/qc_t4 && mkdir -p /tmp/qc_t4
./check_aer_grid.py --date 2008-07-01 --bands sw01 --ceres \
    --outdir /tmp/qc_t4 --no-color
ls /tmp/qc_t4/
```

Expected: both `aer_check_SW01_2008-07-01.txt` and `aer_mean_SW01_2008-07-01.nc` are present.

Then verify the NetCDF mean matches the text report's `global mean`:

```
python -c "
import xarray as xr, numpy as np
ds = xr.open_dataset('/tmp/qc_t4/aer_mean_SW01_2008-07-01.nc')
f = ds['Extinction_Column_Optical_Depth'].values
lat = ds['lat'].values
w = np.cos(np.deg2rad(lat))
finite = np.isfinite(f)
fld = np.where(finite, f, 0.0)
wts = np.where(finite, np.broadcast_to(w[:, None], f.shape), 0.0)
print(f'mean = {fld.sum() * 1.0 / wts.sum() if False else (fld * wts).sum() / wts.sum():.2f}')
print('attrs:')
for k, v in ds.attrs.items():
    print(f'  {k} = {v}')
"
grep 'global mean' /tmp/qc_t4/aer_check_SW01_2008-07-01.txt
```

Expected: the printed `mean = X.XX` matches the `global mean: X.XX` in the text report. The `time_coverage_start = 2008-07-01T00:00:00Z` and `time_coverage_end = 2008-07-01T21:00:00Z` are present, and `n_timesteps_used = 8`, `n_timesteps_expected = 8`, `n_days_with_data = 1`, `n_days_total = 1`.

- [ ] **Step 4: Verify single-day text report still byte-identical**

Run:
```
diff qc/aer_check_SW01_2008-07-01.txt \
     /tmp/qc_t4/aer_check_SW01_2008-07-01.txt
```

Expected: no diff output.

- [ ] **Step 5: Commit**

```bash
git add check_aer_grid.py
git commit -m "check_aer_grid: write per-band NetCDF mean field"
```

---

### Task 5: Range-aware output filenames

Replace the hardcoded `args.date` in the `.txt` and `.nc` output paths with a small helper that picks the single-day or range form based on `date_begin`/`date_end`.

**Files:**
- Modify: `check_aer_grid.py` — add `window_label` helper near `iter_dates`; update the two `os.path.join(args.outdir, ...)` calls in `main()`.

- [ ] **Step 1: Add the label helper**

Insert immediately after `iter_dates`:

```python
def window_label(date_begin, date_end):
    """Return the YYYY-MM-DD or YYYY-MM-DD_to_YYYY-MM-DD string used
    in output filenames and report headers."""
    if date_begin == date_end:
        return date_begin.isoformat()
    return f'{date_begin.isoformat()}_to_{date_end.isoformat()}'
```

- [ ] **Step 2: Use the label in the text-report path**

Find (around line 246-247):

```python
        out_path = os.path.join(
            args.outdir, f'aer_check_{band}_{args.date}.txt')
```

Replace with:

```python
        label = window_label(date_begin, date_end)
        out_path = os.path.join(
            args.outdir, f'aer_check_{band}_{label}.txt')
```

- [ ] **Step 3: Use the label in the NetCDF path**

Find the NetCDF block added in Task 4:

```python
        nc_path = os.path.join(
            args.outdir, f'aer_mean_{band}_{args.date}.nc')
```

Replace with:

```python
        nc_path = os.path.join(
            args.outdir, f'aer_mean_{band}_{label}.nc')
```

- [ ] **Step 4: Verify single-day filename unchanged**

Run:
```
rm -rf /tmp/qc_t5 && mkdir -p /tmp/qc_t5
./check_aer_grid.py --date 2008-07-01 --bands sw01 --ceres \
    --outdir /tmp/qc_t5 --no-color
ls /tmp/qc_t5/
```

Expected exactly:
```
aer_check_SW01_2008-07-01.txt
aer_mean_SW01_2008-07-01.nc
```

- [ ] **Step 5: Verify range filenames produced**

Run:
```
./check_aer_grid.py --date-begin 2008-07-01 --date-end 2008-07-03 \
    --bands sw01 --ceres --outdir /tmp/qc_t5 --no-color
ls /tmp/qc_t5/aer_*2008-07-01_to_2008-07-03*
```

Expected:
```
/tmp/qc_t5/aer_check_SW01_2008-07-01_to_2008-07-03.txt
/tmp/qc_t5/aer_mean_SW01_2008-07-01_to_2008-07-03.nc
```

- [ ] **Step 6: Verify single-day text report still byte-identical**

Run:
```
diff qc/aer_check_SW01_2008-07-01.txt \
     /tmp/qc_t5/aer_check_SW01_2008-07-01.txt
```

Expected: no diff output.

- [ ] **Step 7: Commit**

```bash
git add check_aer_grid.py
git commit -m "check_aer_grid: range-aware output filenames"
```

---

### Task 6: Range-aware text report header

Update `format_report` to emit the spec's range header (`window-mean` title, `range:` line with day count, new `days:` line, source-glob with date wildcards) when more than one date was averaged. The single-day form must remain byte-identical.

**Files:**
- Modify: `check_aer_grid.py` — change `format_report` signature and body (lines 152-191); update the two call sites in `main()` (text-write block and colorized stdout block).

- [ ] **Step 1: Replace `format_report`**

Replace the entire `format_report` function with:

```python
def format_report(band, date_begin, date_end, source_glob, n_found,
                  n_total, n_days_data, n_days_total, stats,
                  colorize=False):
    """Render the full text report for one (band, window).

    date_begin, date_end: datetime.date instances. When equal, the
    header uses the single-day format (byte-identical to the pre-range
    version of this script).

    When colorize=True, cell values are wrapped with ANSI 256-color
    foreground codes; the visual width is unchanged (5 chars per cell).
    """
    is_single_day = (date_begin == date_end)
    lines = []
    if is_single_day:
        lines.append(
            f'AER {band} daily-mean Extinction_Column_Optical_Depth')
        lines.append(f'date:        {date_begin.isoformat()}')
        lines.append(f'source:      {source_glob}')
        lines.append(f'timesteps:   {n_found}/{n_total}')
    else:
        n_days = (date_end - date_begin).days + 1
        lines.append(
            f'AER {band} window-mean Extinction_Column_Optical_Depth')
        lines.append(
            f'range:       {date_begin.isoformat()} to '
            f'{date_end.isoformat()}  ({n_days} days)')
        lines.append(f'source:      {source_glob}')
        lines.append(f'timesteps:   {n_found}/{n_total}')
        lines.append(f'days:        {n_days_data}/{n_days_total}')
    lines.append(f'global mean: {stats["global_mean"]:.2f}'
                 f'  (area-weighted, cos lat)')
    lines.append(f'global min:  {stats["global_min"]:.2f}')
    lines.append(f'global max:  {stats["global_max"]:.2f}')
    nan_cells = int(np.isnan(stats['cells']).sum())
    lines.append(f'NaN cells:   {nan_cells}')
    lines.append(f'NaN points:  {stats["nan_points"]} / '
                 f'{stats["total_points"]}')
    lines.append('')

    # Header row: 4-char indent (under the lat label), then each lon
    # label is right-padded to a 6-char block ('  170W', '   90W', ...).
    header = '    ' + ''.join(f'  {lab}' for lab in LON_LABELS)
    lines.append(header)

    cells = stats['cells']
    for i, lat_lab in enumerate(LAT_LABELS):
        row_vals = []
        for j in range(18):
            v = cells[i, j]
            s = '  NaN' if np.isnan(v) else f'{v:5.2f}'
            if colorize:
                s = _color_cell(s, v)
            row_vals.append(s)
        # 4-char lat label + 6 chars per cell (1 space + 5-char value).
        row = lat_lab + ''.join(' ' + s for s in row_vals)
        lines.append(row)

    return '\n'.join(lines) + '\n'
```

- [ ] **Step 2: Replace `source_glob` construction in `main()`**

For the range case the source pattern needs date wildcards. Find (added in Task 2):

```python
        first_paths = build_paths(args.datadir, args.ceres, dates[0], band)
        source_glob = first_paths[0].replace('T0000.V01.nc4', 'T*.V01.nc4')
```

Replace with:

```python
        first_paths = build_paths(args.datadir, args.ceres, dates[0], band)
        source_glob = first_paths[0].replace('T0000.V01.nc4', 'T*.V01.nc4')
        if not is_single_day:
            # Replace the 8 YYYYMMDD digits in the embedded date with '?'.
            yyyymmdd = dates[0].replace('-', '')
            source_glob = source_glob.replace(yyyymmdd, '????????', 1)
```

- [ ] **Step 3: Update the two `format_report` call sites**

Find (text-write block):

```python
        report = format_report(band, args.date, source_glob, n_found, stats)
```

Replace with:

```python
        report = format_report(
            band, date_begin, date_end, source_glob,
            n_found, n_total, n_days_data, n_days_total, stats)
```

Find (colorized stdout block, a few lines below):

```python
        if do_color:
            sys.stdout.write(format_report(
                band, args.date, source_glob, n_found, stats, colorize=True))
```

Replace with:

```python
        if do_color:
            sys.stdout.write(format_report(
                band, date_begin, date_end, source_glob,
                n_found, n_total, n_days_data, n_days_total, stats,
                colorize=True))
```

- [ ] **Step 4: Update the per-band INFO log line**

Find (one line above the colorized block):

```python
        logging.info('Wrote %s (mean=%.2f, %d/8 timesteps)',
                     out_path, stats['global_mean'], n_found)
```

Replace with:

```python
        logging.info('Wrote %s (mean=%.2f, %d/%d timesteps)',
                     out_path, stats['global_mean'], n_found, n_total)
```

- [ ] **Step 5: Verify single-day text report is still byte-identical**

This is the most important check in the plan. Run:

```
rm -rf /tmp/qc_t6 && mkdir -p /tmp/qc_t6
./check_aer_grid.py --date 2008-07-01 --bands sw01 --ceres \
    --outdir /tmp/qc_t6 --no-color
diff qc/aer_check_SW01_2008-07-01.txt \
     /tmp/qc_t6/aer_check_SW01_2008-07-01.txt
```

Expected: no diff output. If anything prints, **stop** — the report is no longer byte-identical and Task 6 must be revised before continuing.

- [ ] **Step 6: Verify range report has the new header**

Run:
```
./check_aer_grid.py --date-begin 2008-07-01 --date-end 2008-07-03 \
    --bands sw01 --ceres --outdir /tmp/qc_t6 --no-color
head -10 /tmp/qc_t6/aer_check_SW01_2008-07-01_to_2008-07-03.txt
```

Expected (date wildcards in `source:` may use `?` instead of literal digits):
```
AER SW01 window-mean Extinction_Column_Optical_Depth
range:       2008-07-01 to 2008-07-03  (3 days)
source:      /CERES/sarb/dfillmor/GEOSIT_alpha_4/2008/07/GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.AER_SW01.????????T*.V01.nc4
timesteps:   24/24
days:        3/3
global mean: 0.XX  (area-weighted, cos lat)
global min:  0.XX
global max:  X.XX
NaN cells:   0
NaN points:  0 / 51840
```

(`global mean`/`min`/`max` will reflect actual data; the header lines are what we're verifying.)

- [ ] **Step 7: Commit**

```bash
git add check_aer_grid.py
git commit -m "check_aer_grid: range-aware text report header"
```

---

### Task 7: Update README "Quick QC" section

Document the range form and the new `.nc` output. Keep the existing single-day example.

**Files:**
- Modify: `README.md` — `### Quick QC (per-band regional means)` section (lines 87-103).

- [ ] **Step 1: Read the current section**

Run:
```
sed -n '87,104p' README.md
```

Verify it matches what's expected (the existing section ends at the `--color` line ~103).

- [ ] **Step 2: Replace the section body**

Replace the lines from `### Quick QC` through `--color to force on when piped.` with:

```markdown
### Quick QC (per-band regional means)

For a fast text-only sanity check of AER output on bands that have
finished, use `check_aer_grid.py`. It writes two files per (band, window)
under `--outdir`:

- `aer_check_{BAND}_{window}.txt` — global stats and a 9×18
  area-weighted regional-mean map of column AOD.
- `aer_mean_{BAND}_{window}.nc` — the full-resolution 180×288
  time-mean field of `Extinction_Column_Optical_Depth`.

`{window}` is `YYYY-MM-DD` for a single day or
`YYYY-MM-DD_to_YYYY-MM-DD` for a range.

Single-day:
```bash
./check_aer_grid.py --date 2008-07-01 --bands sw01,sw02 --ceres
cat qc/aer_check_SW01_2008-07-01.txt
```

Date range (inclusive on both ends):
```bash
./check_aer_grid.py --date-begin 2008-07-01 --date-end 2008-07-31 \
    --bands sw01 --ceres
cat qc/aer_check_SW01_2008-07-01_to_2008-07-31.txt
ncdump -h qc/aer_mean_SW01_2008-07-01_to_2008-07-31.nc
```

`--date` is mutually exclusive with `--date-begin`/`--date-end`. The
range form averages every available timestep across the window with
equal weight.

Bands can be listed in any combination (`sw01,sw02,lw03,...`). The script
exits non-zero only if a requested band has zero timestep files across
the entire window.

When stdout is a TTY the colorized map is also printed to the terminal
(blue for clean, green/yellow for moderate, orange/red for heavy AOD).
Use `--no-color` to suppress, or `--color` to force on when piped.
```

- [ ] **Step 3: Verify section renders cleanly**

Run:
```
sed -n '87,130p' README.md
```

Spot-check that markdown structure is intact (no broken fences, lists indent normally).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "Document check_aer_grid date-range and NetCDF output in README"
```

---

### Task 8: Final integration smoke test

Exercise the full workflow against real July 2008 data and confirm the spec's verification criteria. This task does not change any code.

**Files:** none modified.

- [ ] **Step 1: Single-day backward compatibility**

Run:
```
rm -rf /tmp/qc_final && mkdir -p /tmp/qc_final
./check_aer_grid.py --date 2008-07-01 --bands sw01 --ceres \
    --outdir /tmp/qc_final --no-color
diff qc/aer_check_SW01_2008-07-01.txt \
     /tmp/qc_final/aer_check_SW01_2008-07-01.txt
```

Expected: no diff output.

- [ ] **Step 2: Single-day NetCDF round-trip**

Run:
```
python -c "
import xarray as xr, numpy as np
ds = xr.open_dataset('/tmp/qc_final/aer_mean_SW01_2008-07-01.nc')
f = ds['Extinction_Column_Optical_Depth'].values
lat = ds['lat'].values
w = np.cos(np.deg2rad(lat))
finite = np.isfinite(f)
fld = np.where(finite, f, 0.0)
wts = np.where(finite, np.broadcast_to(w[:, None], f.shape), 0.0)
print(f'mean = {(fld * wts).sum() / wts.sum():.2f}')
"
grep 'global mean' /tmp/qc_final/aer_check_SW01_2008-07-01.txt
```

Expected: the two values match to two decimals.

- [ ] **Step 3: Full-month range run**

Run:
```
./check_aer_grid.py --date-begin 2008-07-01 --date-end 2008-07-31 \
    --bands sw01 --ceres --outdir /tmp/qc_final --no-color
ls /tmp/qc_final/
```

Expected: both
```
aer_check_SW01_2008-07-01_to_2008-07-31.txt
aer_mean_SW01_2008-07-01_to_2008-07-31.nc
```
are present (alongside the single-day pair from Step 1).

- [ ] **Step 4: Inspect the range report and NetCDF metadata**

Run:
```
head -10 /tmp/qc_final/aer_check_SW01_2008-07-01_to_2008-07-31.txt
ncdump -h /tmp/qc_final/aer_mean_SW01_2008-07-01_to_2008-07-31.nc | \
    grep -E ':(time_coverage_|n_timesteps_|n_days_|band|source)'
```

Expected from the report:
- Title line: `AER SW01 window-mean Extinction_Column_Optical_Depth`
- `range: 2008-07-01 to 2008-07-31  (31 days)`
- `timesteps: 248/248` (or close — warns about any genuinely missing files)
- `days: 31/31`

Expected from `ncdump -h`:
- `time_coverage_start = "2008-07-01T00:00:00Z"`
- `time_coverage_end = "2008-07-31T21:00:00Z"`
- `n_timesteps_used` matches the report's numerator
- `n_timesteps_expected = 248`
- `n_days_total = 31`
- `band = "SW01"`

- [ ] **Step 5: CLI validation regression check**

Run each, confirming exit code 2 and a usage/error message:
```
./check_aer_grid.py --date 2008-07-01 --date-begin 2008-07-01 --date-end 2008-07-02 --bands sw01; echo "exit=$?"
./check_aer_grid.py --date-begin 2008-07-01 --bands sw01; echo "exit=$?"
./check_aer_grid.py --date-begin 2008-07-31 --date-end 2008-07-01 --bands sw01; echo "exit=$?"
./check_aer_grid.py --bands sw01; echo "exit=$?"
```

Each must print `exit=2`.

- [ ] **Step 6: Done — no commit needed**

This task is verification only.

---

## Out of scope (from the spec)

- Changes to other plot/QC scripts.
- A pytest suite for `check_aer_grid.py`.
- Equal-day weighting (Approach 2) or streaming reduction (Approach 3).
- Any change to source-data layout, the 9×18 cell aggregation math, or
  the colorized stdout output's color thresholds.
