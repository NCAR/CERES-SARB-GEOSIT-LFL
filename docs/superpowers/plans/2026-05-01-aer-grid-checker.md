# AER per-band grid checker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `check_aer_grid.py`, a standalone, plot-free, per-band sanity checker that writes one text file per (band, date) containing a 9×18 area-weighted regional-mean map of column AOD plus global stats.

**Architecture:** Single new Python script at the project root. Five internal functions composed in `main`: path construction → daily-mean loading → 9×18 cell aggregation with cos-lat weighting → text formatting → multi-band orchestration. No modifications to existing files.

**Tech Stack:** Python 3, numpy, xarray, argparse, logging. No new dependencies. Conda env `sarb` (already activated by users via the existing wrappers).

**Spec:** `docs/superpowers/specs/2026-05-01-aer-grid-checker-design.md`

**Testing approach:** This project has no existing test framework (no `tests/`, no pytest config, sibling scripts have no tests). The approved spec specifies manual verification. Each task ends with a concrete verification step — REPL-style sanity checks on synthetic data for arithmetic-heavy tasks, real-data invocations for integration tasks. The script itself stays under one file.

---

### Task 1: Script skeleton + CLI

Create the script with argparse and an empty main loop. Verify `--help` renders.

**Files:**
- Create: `check_aer_grid.py`

- [ ] **Step 1: Create the script skeleton**

```python
#!/usr/bin/env python
"""Per-band AER aggregate sanity checker.

Reads daily AER_{band} output, computes a 9x18 area-weighted regional-mean
map of Extinction_Column_Optical_Depth, and writes one text file per
(band, date) under --outdir.
"""

import argparse
import logging
import os
import sys


def main():
    parser = argparse.ArgumentParser(
        description='Per-band AER aggregate sanity checker (text 9x18 map)')
    parser.add_argument('--date', type=str, required=True,
                        help='date YYYY-MM-DD')
    parser.add_argument('--bands', type=str, required=True,
                        help='comma-separated band list, e.g. sw01,sw02,lw03')
    parser.add_argument('--datadir', type=str,
                        default=os.path.join(os.getenv('HOME'), 'Data'),
                        help='top-level data directory (default $HOME/Data)')
    parser.add_argument('--outdir', type=str, default='qc',
                        help='output directory (default qc)')
    parser.add_argument('--ceres', action='store_true',
                        help='use CERES production paths (GEOSIT_alpha_4)')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)s %(message)s')
    os.makedirs(args.outdir, exist_ok=True)

    bands = [b.strip().upper() for b in args.bands.split(',') if b.strip()]
    if not bands:
        parser.error('--bands must contain at least one band')

    any_failed = False
    for band in bands:
        # filled in by later tasks
        logging.info('Would process %s for %s', band, args.date)

    sys.exit(1 if any_failed else 0)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Make executable, verify --help**

Run:
```
chmod +x check_aer_grid.py
./check_aer_grid.py --help
```

Expected: argparse usage block listing all five flags. No exception.

- [ ] **Step 3: Verify happy-path no-op execution**

Run:
```
./check_aer_grid.py --date 2008-07-01 --bands sw01,sw02 --outdir /tmp/qc_test
```

Expected: two `INFO Would process SW01 for 2008-07-01` / `SW02 for 2008-07-01` lines, exit 0. Confirms band normalization (lowercase → uppercase) and `--bands` parsing.

- [ ] **Step 4: Commit**

```
git add check_aer_grid.py
git commit -m "Add check_aer_grid.py skeleton with CLI"
```

---

### Task 2: File-path construction

Add the function that builds the 8 expected timestep paths for a given (band, date), matching the existing FILE_PATTERN from `validate_run.py`.

**Files:**
- Modify: `check_aer_grid.py`

- [ ] **Step 1: Add path-builder function**

Insert before `def main()`:

```python
TIMESTEPS = ['T0000', 'T0300', 'T0600', 'T0900',
             'T1200', 'T1500', 'T1800', 'T2100']


def build_paths(datadir, ceres, date, band):
    """Return the 8 expected timestep file paths for one (band, date).

    date: 'YYYY-MM-DD'
    band: uppercase, e.g. 'SW01'
    """
    yyyy, mm, _ = date.split('-')
    if ceres:
        base = '/CERES/sarb/dfillmor'
        subdir = 'GEOSIT_alpha_4'
    else:
        base = datadir
        subdir = 'GEOSIT'
    fname_tmpl = (
        'GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.'
        'AER_{band}.{date}{ts}.V01.nc4'
    )
    return [
        os.path.join(base, subdir, yyyy, mm,
                     fname_tmpl.format(band=band, date=date, ts=ts))
        for ts in TIMESTEPS
    ]
```

- [ ] **Step 2: Wire into main with a debug print**

In `main`, replace the body of the `for band in bands:` loop with:

```python
        paths = build_paths(args.datadir, args.ceres, args.date, band)
        for p in paths:
            print(p)
```

- [ ] **Step 3: Verify CERES paths**

Run:
```
./check_aer_grid.py --date 2008-07-01 --bands sw01 --ceres --outdir /tmp/qc_test
```

Expected first line:
```
/CERES/sarb/dfillmor/GEOSIT_alpha_4/2008/07/GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.AER_SW01.2008-07-01T0000.V01.nc4
```
Followed by 7 more lines for T0300 through T2100.

Confirm by running the same path through `ls`:
```
ls /CERES/sarb/dfillmor/GEOSIT_alpha_4/2008/07/GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.AER_SW01.2008-07-01T0000.V01.nc4
```
Expected: file exists (production run output). If it does not, ask the user before continuing — the path convention may have changed.

- [ ] **Step 4: Verify non-CERES paths**

Run:
```
./check_aer_grid.py --date 2008-07-01 --bands sw01 --datadir /tmp/fakedata --outdir /tmp/qc_test
```

Expected first line:
```
/tmp/fakedata/GEOSIT/2008/07/GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.AER_SW01.2008-07-01T0000.V01.nc4
```

- [ ] **Step 5: Remove the debug print**

In `main`, the `for p in paths: print(p)` debug loop is replaced in the next task. For now just confirm it's still there — Task 3 will replace it.

- [ ] **Step 6: Commit**

```
git add check_aer_grid.py
git commit -m "check_aer_grid: build per-band timestep file paths"
```

---

### Task 3: Daily-mean loading

Open the timestep files, average over time, return the 2D field plus lat/lon and the count of timesteps actually found.

**Files:**
- Modify: `check_aer_grid.py`

- [ ] **Step 1: Add the loader**

At the top of the file, add `import numpy as np` and `import xarray as xr` to the existing imports.

Insert before `def main()`:

```python
def load_daily_mean(paths):
    """Load AER aggregate timestep files and average over time.

    Returns (field, lat, lon, n_found) where field is shape (180, 288)
    and lat/lon are 1-D arrays read from the file. Missing timesteps
    are skipped with a WARNING. NaNs in input propagate via nanmean.
    """
    fields = []
    lat = lon = None
    for p in paths:
        if not os.path.exists(p):
            logging.warning('Missing timestep: %s', p)
            continue
        ds = xr.open_dataset(p)
        arr = ds['Extinction_Column_Optical_Depth'].values
        # File stores either (time, lat, lon) with time=1 or (lat, lon).
        if arr.ndim == 3:
            arr = arr[0]
        fields.append(arr.astype(np.float64))
        if lat is None:
            lat = ds['lat'].values.astype(np.float64)
            lon = ds['lon'].values.astype(np.float64)
        ds.close()
    if not fields:
        return None, None, None, 0
    daily = np.nanmean(np.stack(fields), axis=0)
    return daily, lat, lon, len(fields)
```

- [ ] **Step 2: Wire into main, replace the debug print**

In `main`, replace the path-printing loop body with:

```python
        paths = build_paths(args.datadir, args.ceres, args.date, band)
        field, lat, lon, n_found = load_daily_mean(paths)
        if n_found == 0:
            logging.error('No timestep files found for %s %s', band, args.date)
            any_failed = True
            continue
        logging.info('%s: loaded %d/8 timesteps; field shape %s; '
                     'min=%.4f max=%.4f',
                     band, n_found, field.shape,
                     float(np.nanmin(field)), float(np.nanmax(field)))
```

- [ ] **Step 3: Verify on real production data**

Run:
```
./check_aer_grid.py --date 2008-07-01 --bands sw01,sw02 --ceres
```

Expected output (one line per band):
```
INFO SW01: loaded 8/8 timesteps; field shape (180, 288); min=... max=...
INFO SW02: loaded 8/8 timesteps; field shape (180, 288); min=... max=...
```

Sanity-check the values: AOD should be non-negative and well below 10. If `min` is negative or `max` is unreasonably large, stop and inspect the data before proceeding.

- [ ] **Step 4: Verify shape and lat/lon ranges interactively**

Run:
```
python -c "
import xarray as xr
ds = xr.open_dataset('/CERES/sarb/dfillmor/GEOSIT_alpha_4/2008/07/GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.AER_SW01.2008-07-01T0000.V01.nc4')
print('vars:', list(ds.data_vars))
print('lat:', ds.lat.values[0], '...', ds.lat.values[-1], 'len=', len(ds.lat))
print('lon:', ds.lon.values[0], '...', ds.lon.values[-1], 'len=', len(ds.lon))
print('arr shape:', ds['Extinction_Column_Optical_Depth'].shape)
"
```

Confirm:
- `vars:` includes `Extinction_Column_Optical_Depth`
- `lat` length 180 (range approx ±89.5)
- `lon` length 288
- array shape is `(1, 180, 288)` or `(180, 288)` — both branches covered in step 1.

If the variable name is different, update the loader accordingly and re-verify.

- [ ] **Step 5: Commit**

```
git add check_aer_grid.py
git commit -m "check_aer_grid: load and time-average AER timestep files"
```

---

### Task 4: 9×18 cell aggregation with cos-lat weighting

Reshape the 180×288 field into 9×18 cells, area-weight by cos(lat) per native point, compute cell means and global stats. Always output north-to-south.

**Files:**
- Modify: `check_aer_grid.py`

- [ ] **Step 1: Add the aggregator**

Insert before `def main()`:

```python
def aggregate_cells(field, lat):
    """Reduce a (180, 288) field to a 9x18 area-weighted cell-mean grid.

    Returns dict with:
        cells:      (9, 18) array, north-to-south rows, west-to-east cols.
                    NaN if a cell has zero finite, positive-weight points.
        global_mean, global_min, global_max: scalars (nanstats over field).
        nan_points: count of NaN points in the input field.
        total_points: total points in the input field (180*288).
    """
    if field.shape != (180, 288):
        raise ValueError(f'expected (180, 288), got {field.shape}')
    if lat.shape != (180,):
        raise ValueError(f'expected lat shape (180,), got {lat.shape}')

    # Orient north-to-south. The output map's top row is 80N.
    if lat[0] < lat[-1]:
        field = field[::-1, :]
        lat = lat[::-1]

    weights = np.cos(np.deg2rad(lat))                  # (180,)
    w2d = np.broadcast_to(weights[:, None], field.shape)  # (180, 288)

    finite = np.isfinite(field)
    fld = np.where(finite, field, 0.0)
    wts = np.where(finite, w2d, 0.0)

    # Reshape (180, 288) -> (9, 20, 18, 16) so axes (1, 3) are within-cell.
    f4 = fld.reshape(9, 20, 18, 16)
    w4 = wts.reshape(9, 20, 18, 16)

    num = (f4 * w4).sum(axis=(1, 3))   # (9, 18)
    den = w4.sum(axis=(1, 3))          # (9, 18) -- sum of weights
    cells = np.where(den > 0, num / den, np.nan)

    global_num = (fld * wts).sum()
    global_den = wts.sum()
    global_mean = global_num / global_den if global_den > 0 else float('nan')
    global_min = float(np.nanmin(field)) if finite.any() else float('nan')
    global_max = float(np.nanmax(field)) if finite.any() else float('nan')
    nan_points = int((~finite).sum())
    total_points = int(field.size)

    return {
        'cells': cells,
        'global_mean': float(global_mean),
        'global_min': global_min,
        'global_max': global_max,
        'nan_points': nan_points,
        'total_points': total_points,
    }
```

- [ ] **Step 2: Verify on a constant field**

Run:
```
python -c "
import numpy as np
import sys; sys.path.insert(0, '.')
from check_aer_grid import aggregate_cells
field = np.full((180, 288), 0.42)
lat = np.linspace(-89.5, 89.5, 180)
out = aggregate_cells(field, lat)
print('cells unique:', np.unique(out['cells']))
print('global_mean:', out['global_mean'])
print('orient (top row mean vs bottom row mean):',
      out['cells'][0].mean(), out['cells'][-1].mean())
"
```

Expected:
- `cells unique: [0.42]`
- `global_mean: 0.42`
- top and bottom row both 0.42

- [ ] **Step 3: Verify cos-lat weighting kicks in correctly**

Run:
```
python -c "
import numpy as np
import sys; sys.path.insert(0, '.')
from check_aer_grid import aggregate_cells
# Field = cos(lat). Cell mean = (sum cos^2 / sum cos) per row.
lat = np.linspace(-89.5, 89.5, 180)
field = np.broadcast_to(np.cos(np.deg2rad(lat))[:, None], (180, 288)).copy()
out = aggregate_cells(field, lat)
# Top row covers lat 70..90, weighted-mean of cos(lat) over those 20 points.
top_lat = lat[lat > 70]              # 20 points centered around 80
w = np.cos(np.deg2rad(top_lat))
expected = (w * w).sum() / w.sum()
print('top row cell value:', out['cells'][0, 0])
print('expected:           ', expected)
assert abs(out['cells'][0, 0] - expected) < 1e-12
print('OK')
"
```

Expected: prints the two values (equal to ~12 decimals) and `OK`. If `assert` fails, the weighting or reshape is wrong — fix before continuing.

- [ ] **Step 4: Verify N-to-S orientation regardless of input**

Run:
```
python -c "
import numpy as np
import sys; sys.path.insert(0, '.')
from check_aer_grid import aggregate_cells
lat = np.linspace(-89.5, 89.5, 180)
# Field = lat (so northern row should be ~+80, southern row ~-80).
field = np.broadcast_to(lat[:, None].astype(float), (180, 288)).copy()
# Pass S-to-N (file-style ascending) and confirm output is N-to-S.
out_asc = aggregate_cells(field, lat)
print('asc top:', out_asc['cells'][0, 0], 'bottom:', out_asc['cells'][-1, 0])
# Pass N-to-S (descending) and confirm output is still N-to-S.
out_desc = aggregate_cells(field[::-1], lat[::-1])
print('desc top:', out_desc['cells'][0, 0], 'bottom:', out_desc['cells'][-1, 0])
assert out_asc['cells'][0, 0] > 0 and out_asc['cells'][-1, 0] < 0
assert abs(out_asc['cells'][0, 0] - out_desc['cells'][0, 0]) < 1e-12
print('OK')
"
```

Expected: top row is positive (~+80), bottom row is negative (~-80), orientation invariant under input lat reversal, prints `OK`.

- [ ] **Step 5: Verify NaN handling**

Run:
```
python -c "
import numpy as np
import sys; sys.path.insert(0, '.')
from check_aer_grid import aggregate_cells
lat = np.linspace(-89.5, 89.5, 180)        # ascending, S to N
field = np.full((180, 288), 0.5)
# Put NaN block in the northern hemisphere (last 20 rows of ascending input).
# After aggregate_cells flips N-to-S, this lands in cell (0, 0) of the output.
field[-20:, :16] = np.nan
out = aggregate_cells(field, lat)
print('nan cell:', out['cells'][0, 0])  # expect nan (top-left, north)
print('next cell:', out['cells'][0, 1]) # expect 0.5
print('nan_points:', out['nan_points'], '/', out['total_points'])
assert np.isnan(out['cells'][0, 0])
assert abs(out['cells'][0, 1] - 0.5) < 1e-12
assert out['nan_points'] == 320
print('OK')
"
```

Expected: NaN cell is NaN, neighbours unaffected, `nan_points == 320`, prints `OK`.

- [ ] **Step 6: Commit**

```
git add check_aer_grid.py
git commit -m "check_aer_grid: 9x18 cell aggregation with cos-lat weighting"
```

---

### Task 5: Text formatting

Render the header block plus the labelled 9×18 map.

**Width math (do this in your head before writing the function):**
- Lat label = 4 chars (e.g., `' 80N'`).
- Each cell occupies 6 chars on a data row: `' '` separator + `%5.2f` value.
- Data row width = 4 + 18 × 6 = 112 chars.
- Header row matches if the indent is 4 chars (where the lat label would go) and each lon label occupies 6 chars too: 4 + 18 × 6 = 112 chars.
- Each 4-char lon label (`'170W'`, `' 90W'`, …) is right-padded into a 6-char block by a 2-space prefix, so the label's last character lands above the cell value's last digit.

**Files:**
- Modify: `check_aer_grid.py`

- [ ] **Step 1: Add the formatter**

Insert before `def main()`:

```python
LON_LABELS = ['170W', '150W', '130W', '110W', ' 90W', ' 70W', ' 50W',
              ' 30W', ' 10W', ' 10E', ' 30E', ' 50E', ' 70E', ' 90E',
              '110E', '130E', '150E', '170E']
LAT_LABELS = [' 80N', ' 60N', ' 40N', ' 20N', '  0 ',
              ' 20S', ' 40S', ' 60S', ' 80S']


def format_report(band, date, source_glob, n_found, stats):
    """Render the full text report for one (band, date)."""
    lines = []
    lines.append(f'AER {band} daily-mean Extinction_Column_Optical_Depth')
    lines.append(f'date:        {date}')
    lines.append(f'source:      {source_glob}')
    lines.append(f'timesteps:   {n_found}/8')
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
            if np.isnan(v):
                row_vals.append('  NaN')
            else:
                row_vals.append(f'{v:5.2f}')
        # 4-char lat label + 6 chars per cell (1 space + 5-char value).
        row = lat_lab + ''.join(' ' + s for s in row_vals)
        lines.append(row)

    return '\n'.join(lines) + '\n'
```

- [ ] **Step 2: Verify alignment with synthetic data**

Run:
```
python -c "
import numpy as np
import sys; sys.path.insert(0, '.')
from check_aer_grid import aggregate_cells, format_report
lat = np.linspace(-89.5, 89.5, 180)
field = np.full((180, 288), 0.123)
field[:20, :16] = np.nan
stats = aggregate_cells(field, lat)
print(format_report('SW01', '2008-07-01', '/path/to/AER_SW01.*', 8, stats))
"
```

Expected:
- Header block followed by a longitude header row, then 9 data rows starting with ` 80N`, ` 60N`, …, ` 80S`.
- Top-left cell shows `  NaN`; all other cells show ` 0.12`.
- Column alignment: each lon label's last character (`W` or `E`) sits in the same column as the units digit of the cell values below. Confirm this with `head -n 20 | cat -A` if needed, or by visual inspection at terminal width ≥ 115.
- Final data-row line length: 112 chars. Quick check:

```
python -c "
import numpy as np, sys; sys.path.insert(0, '.')
from check_aer_grid import aggregate_cells, format_report
lat = np.linspace(-89.5, 89.5, 180)
stats = aggregate_cells(np.full((180, 288), 0.12), lat)
out = format_report('SW01', '2008-07-01', 'x', 8, stats)
data_lines = out.splitlines()[-9:]
hdr_line = out.splitlines()[-10]
print('hdr len:', len(hdr_line), 'data lens:', set(len(l) for l in data_lines))
assert len(hdr_line) == 112
assert set(len(l) for l in data_lines) == {112}
print('OK')
"
```

Expected: `hdr len: 112 data lens: {112}` and `OK`.

- [ ] **Step 3: Commit**

```
git add check_aer_grid.py
git commit -m "check_aer_grid: format text report with lat/lon-labelled map"
```

---

### Task 6: Wire it together, write per-band files, verify on real data

Compose all functions, write the output file per band, drive the `any_failed` exit-code path.

**Files:**
- Modify: `check_aer_grid.py`

- [ ] **Step 1: Replace the `for band` body in main**

Replace the in-loop debug block from Task 3 with:

```python
        paths = build_paths(args.datadir, args.ceres, args.date, band)
        field, lat, lon, n_found = load_daily_mean(paths)
        if n_found == 0:
            logging.error('No timestep files found for %s %s',
                          band, args.date)
            any_failed = True
            continue
        stats = aggregate_cells(field, lat)
        # Use a glob-style source string so the report shows the pattern
        # rather than 8 individual paths.
        source_glob = paths[0].replace('T0000.V01.nc4', 'T*.V01.nc4')
        report = format_report(band, args.date, source_glob, n_found, stats)
        out_path = os.path.join(
            args.outdir, f'aer_check_{band}_{args.date}.txt')
        with open(out_path, 'w') as f:
            f.write(report)
        logging.info('Wrote %s (mean=%.2f, %d/8 timesteps)',
                     out_path, stats['global_mean'], n_found)
```

- [ ] **Step 2: End-to-end run on real production data**

Run:
```
./check_aer_grid.py --date 2008-07-01 --bands sw01,sw02 --ceres
```

Expected:
- `INFO Wrote qc/aer_check_SW01_2008-07-01.txt (mean=..., 8/8 timesteps)`
- `INFO Wrote qc/aer_check_SW02_2008-07-01.txt (mean=..., 8/8 timesteps)`
- exit 0

- [ ] **Step 3: Eyeball the output**

Run:
```
cat qc/aer_check_SW01_2008-07-01.txt
```

Confirm:
- Header block: date, source path, `timesteps: 8/8`, global mean/min/max with 2 decimals, NaN counts.
- Map: 9 rows, 18 columns. Column header labels align over the cell values below.
- Top row (` 80N`) shows lower AOD over polar regions. NH summer (July) should show heavier AOD in NH mid-latitudes (Saharan dust, biomass-burning) than the SH equivalents — visible as larger values in the ` 20N`/` 40N` rows over Africa/Asia longitudes than the matching ` 20S`/` 40S` rows.
- No negative values, no NaN cells (assuming a healthy production run).

If global mean is negative, NaN, or wildly out of range (>5), stop and investigate before declaring success.

- [ ] **Step 4: Verify the missing-file exit-code path**

Pick a date that does not exist in the production directory:

```
./check_aer_grid.py --date 2099-01-01 --bands sw01 --ceres
echo "exit=$?"
```

Expected:
- 8 `WARNING Missing timestep: ...` lines.
- `ERROR No timestep files found for SW01 2099-01-01`.
- `exit=1`.
- No file written under `qc/`.

- [ ] **Step 5: Verify the partial-files path**

Run on a band that has only some timesteps available (the user mentioned the production run is in progress). Pick a band that is currently mid-processing — for example, if SW03 has only the early timesteps:

```
./check_aer_grid.py --date 2008-07-01 --bands sw03 --ceres
```

Expected:
- WARNING lines for each missing timestep.
- File written, header line `timesteps: N/8` with N < 8.
- exit 0 (partial success is success).

If no band is currently partial, simulate by pointing at a non-CERES `--datadir` containing only some of the files. Skip this step if no partial state is reproducible — Task 4's NaN tests already exercise the underlying nanmean path.

- [ ] **Step 6: Commit**

```
git add check_aer_grid.py
git commit -m "check_aer_grid: wire pipeline and write per-band text reports"
```

---

### Task 7: Document the script in README

Add a one-paragraph entry to README.md so future users know the script exists.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a "Quick QC" section after "Monitoring and Managing Jobs"**

Append to `README.md`:

```markdown

### Quick QC (per-band regional means)

For a fast text-only sanity check of AER output on bands that have
finished, use `check_aer_grid.py`. It writes one text file per (band, date)
with global stats and a 9×18 area-weighted regional-mean map of column AOD.

```bash
./check_aer_grid.py --date 2008-07-01 --bands sw01,sw02 --ceres
cat qc/aer_check_SW01_2008-07-01.txt
```

Bands can be listed in any combination (`sw01,sw02,lw03,...`). The script
exits non-zero only if a requested band has zero timestep files.
```

- [ ] **Step 2: Verify the README renders cleanly**

```
git diff README.md
```

Confirm: no broken markdown, code fences balanced, section integrates into the existing structure.

- [ ] **Step 3: Commit**

```
git add README.md
git commit -m "Document check_aer_grid.py in README"
```

---

## Self-Review

**Spec coverage:**
- Invocation flags (`--date`, `--bands`, `--datadir`, `--outdir`, `--ceres`) — Task 1.
- File-path construction matching `validate_run.py` FILE_PATTERN — Task 2.
- 8-timestep load + daily nanmean — Task 3.
- 9×18 reshape, cos-lat weighting (per native point), N→S orientation — Task 4.
- Global mean/min/max, NaN-cell and NaN-point counts — Tasks 4 & 5.
- Header block + lat/lon labels + `%5.2f` cells, `  NaN` for all-NaN cells — Task 5.
- Per-band exit handling: 0 timesteps → exit 1 for that band, 1–7 → write file with N/8, 8 → normal — Tasks 3 & 6.
- LW bands handled by uppercase normalization, no special-casing — Task 1.
- Output dir `qc/` created on demand — Task 1.

**Placeholder scan:** No TBDs, all code blocks contain real code, all expected outputs are concrete.

**Type consistency:** `aggregate_cells` returns a dict with keys `cells`, `global_mean`, `global_min`, `global_max`, `nan_points`, `total_points`; `format_report` reads exactly those keys plus computes `nan_cells` from `cells`. `build_paths` returns `list[str]`; `load_daily_mean` returns `(field, lat, lon, n_found)` consumed positionally.

**Out-of-scope confirmed absent from plan:** no plots, no per-species, no pipeline integration, no comparison-to-reference.
