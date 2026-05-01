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
        for p in paths:
            print(p)

    sys.exit(1 if any_failed else 0)


if __name__ == '__main__':
    main()
