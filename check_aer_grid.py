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


def iter_dates(begin, end):
    """Yield 'YYYY-MM-DD' strings for begin..end inclusive.

    begin, end: datetime.date instances. end >= begin.
    """
    n = (end - begin).days + 1
    for i in range(n):
        yield (begin + datetime.timedelta(days=i)).isoformat()


def window_label(date_begin, date_end):
    """Return the YYYY-MM-DD or YYYY-MM-DD_to_YYYY-MM-DD string used
    in output filenames and report headers."""
    if date_begin == date_end:
        return date_begin.isoformat()
    return f'{date_begin.isoformat()}_to_{date_end.isoformat()}'


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


def load_window_mean(datadir, ceres, dates, band):
    """Average Extinction_Column_Optical_Depth over all available
    timesteps in the window.

    dates: list of 'YYYY-MM-DD' strings, in any order.
    band:  uppercase, e.g. 'SW01'.

    Returns:
        field:               (180, 288) float64, np.nanmean over the
                             full stack of available timestep arrays,
                             or None if zero timesteps were found or a
                             lat-shape mismatch aborted the band.
        lat, lon:            1-D arrays from the first file read, or
                             None if zero timesteps were found or a
                             lat-shape mismatch aborted the band.
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

# Discretized AOD bins used when --color is on. 5 cuts -> 6 bins, indexed
# by sum(v >= cut for cut in LEVELS) so 0 = cleanest, 5 = extreme.
LEVELS = [0.05, 0.10, 0.20, 0.50, 1.00]
# ANSI 256-color foreground codes per bin (sequential blue->cyan->green
# ->yellow->orange->red). NaN gets a distinct magenta.
LEVEL_FG_COLORS = [27, 39, 46, 226, 208, 196]
NAN_FG_COLOR = 165


def _color_cell(text, v):
    """Wrap a 5-char cell string with an ANSI 256-color foreground."""
    if np.isnan(v):
        code = NAN_FG_COLOR
    else:
        code = LEVEL_FG_COLORS[sum(v >= cut for cut in LEVELS)]
    return f'\x1b[38;5;{code}m{text}\x1b[0m'


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
                + datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
            ),
        },
    )
    ds.to_netcdf(out_path, format='NETCDF4_CLASSIC')


def main():
    parser = argparse.ArgumentParser(
        description='Per-band AER aggregate sanity checker (text 9x18 map)')
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
    parser.add_argument('--bands', type=str, required=True,
                        help='comma-separated band list, e.g. sw01,sw02,lw03')
    parser.add_argument('--datadir', type=str,
                        default=os.path.join(os.getenv('HOME'), 'Data'),
                        help='top-level data directory (default $HOME/Data)')
    parser.add_argument('--outdir', type=str, default='qc',
                        help='output directory (default qc)')
    parser.add_argument('--ceres', action='store_true',
                        help='use CERES production paths (GEOSIT_alpha_4)')
    color_group = parser.add_mutually_exclusive_group()
    color_group.add_argument('--color', dest='color', action='store_const',
                             const=True, default=None,
                             help='colorize stdout cell values by AOD level '
                                  '(default: auto when stdout is a TTY)')
    color_group.add_argument('--no-color', dest='color', action='store_const',
                             const=False,
                             help='disable colorized stdout output')
    args = parser.parse_args()

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

    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)s %(message)s')
    os.makedirs(args.outdir, exist_ok=True)

    bands = [b.strip().upper() for b in args.bands.split(',') if b.strip()]
    if not bands:
        parser.error('--bands must contain at least one band')

    do_color = args.color if args.color is not None else sys.stdout.isatty()

    any_failed = False
    for band in bands:
        field, lat, lon, n_found, n_total, n_days_data, n_days_total = (
            load_window_mean(args.datadir, args.ceres, dates, band))
        if n_found == 0:
            logging.error('Skipping band %s: no usable data in window', band)
            any_failed = True
            continue
        stats = aggregate_cells(field, lat)
        # Use a glob-style source string so the report shows the pattern
        # rather than every individual path.
        first_paths = build_paths(args.datadir, args.ceres, dates[0], band)
        source_glob = first_paths[0].replace('T0000.V01.nc4', 'T*.V01.nc4')
        if not is_single_day:
            # Replace the 10-char YYYY-MM-DD date in the embedded path with '?'.
            source_glob = source_glob.replace(dates[0], '??????????', 1)
        report = format_report(
            band, date_begin, date_end, source_glob,
            n_found, n_total, n_days_data, n_days_total, stats)
        label = window_label(date_begin, date_end)
        out_path = os.path.join(
            args.outdir, f'aer_check_{band}_{label}.txt')
        with open(out_path, 'w') as f:
            f.write(report)
        logging.info('Wrote %s (mean=%.2f, %d/%d timesteps)',
                     out_path, stats['global_mean'], n_found, n_total)
        if do_color:
            sys.stdout.write(format_report(
                band, date_begin, date_end, source_glob,
                n_found, n_total, n_days_data, n_days_total, stats,
                colorize=True))

        nc_path = os.path.join(
            args.outdir, f'aer_mean_{band}_{label}.nc')
        write_mean_netcdf(
            nc_path, field, lat, lon, band, source_glob,
            n_found, n_total, n_days_data, n_days_total,
            date_begin, date_end)
        logging.info('Wrote %s', nc_path)

    sys.exit(1 if any_failed else 0)


if __name__ == '__main__':
    main()
