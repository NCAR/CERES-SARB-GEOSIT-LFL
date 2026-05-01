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
