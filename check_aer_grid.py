#!/usr/bin/env python
"""Per-band AER aggregate sanity checker.

Reads daily AER_{band} output, computes a 9x18 area-weighted regional-mean
map of Extinction_Column_Optical_Depth, and writes one text file per
(band, date) under --outdir.
"""

import argparse
import datetime
import logging
import os
import sys

import numpy as np
import xarray as xr


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
        with xr.open_dataset(p) as ds:
            arr = ds['Extinction_Column_Optical_Depth'].values
            # File stores either (time, lat, lon) with time=1 or (lat, lon).
            if arr.ndim == 3:
                arr = arr[0]
            fields.append(arr.astype(np.float64))
            if lat is None:
                lat = ds['lat'].values.astype(np.float64)
                lon = ds['lon'].values.astype(np.float64)
    if not fields:
        return None, None, None, 0
    daily = np.nanmean(np.stack(fields), axis=0)
    return daily, lat, lon, len(fields)


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

    try:
        datetime.date.fromisoformat(args.date)
    except ValueError:
        parser.error(f"--date must be YYYY-MM-DD, got {args.date!r}")

    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)s %(message)s')
    os.makedirs(args.outdir, exist_ok=True)

    bands = [b.strip().upper() for b in args.bands.split(',') if b.strip()]
    if not bands:
        parser.error('--bands must contain at least one band')

    any_failed = False
    for band in bands:
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

    sys.exit(1 if any_failed else 0)


if __name__ == '__main__':
    main()
