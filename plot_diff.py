import os
import sys
import argparse
import logging
import numpy as np
import pandas as pd
import xarray as xr
import cartopy

mpl_dir = os.path.join('/tmp', 'matplotlib')
os.makedirs(mpl_dir, exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR', mpl_dir)

cartopy_data_dir = os.path.join('/tmp', 'cartopy')
os.makedirs(cartopy_data_dir, exist_ok=True)
cartopy.config['data_dir'] = cartopy_data_dir

from plots import plot_lon_lat


def process_diff(band, species_a, species_b, file_a, file_b, plotfile):

    logging.info('Opening %s', file_a)
    logging.info('Opening %s', file_b)

    ds_a = xr.open_dataset(file_a)
    ds_b = xr.open_dataset(file_b)

    field_a = ds_a['Extinction_Column_Optical_Depth']
    field_b = ds_b['Extinction_Column_Optical_Depth']
    diff = field_a - field_b

    vmax = float(np.nanmax(np.abs(diff.values)))
    if not np.isfinite(vmax) or vmax <= 0:
        vmax = 0.01
    step = vmax / 10
    levels = np.linspace(-vmax, vmax, 21)

    plot_params = {
        'levels': levels,
        'augment_levels': [],
        'coastlines': True,
    }

    title = f'GEOSIT {species_a} - {species_b} AOD {band.upper()}'

    plot_lon_lat(plotfile, title, plot_params, diff, symmetric=True)


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--logfile', type=str, default=sys.stdout,
        help='log file (default stdout)')
    parser.add_argument('--debug', action='store_true',
        help='set logging level to debug')
    parser.add_argument('--datadir', type=str,
        default=os.path.join(os.getenv('HOME'), 'Data'),
        help='top-level data directory (default $HOME/Data)')
    parser.add_argument('--outdir', type=str,
        default=os.path.join(os.getenv('HOME'), 'Plots'),
        help='output directory for plots (default $HOME/Plots)')
    parser.add_argument('--band', type=str, default='sw01')
    parser.add_argument('--species_a', type=str, required=True,
        help='first species code (e.g., SO4)')
    parser.add_argument('--species_b', type=str, required=True,
        help='second species code (e.g., SO4002)')
    parser.add_argument('--datetime', type=str,
        default='2010-01-01T00',
        help='datetime for file selection (YYYY-MM-DDTHH)')
    parser.add_argument('--ceres', action='store_true',
        help='use CERES production paths')
    args = parser.parse_args()

    logging_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(stream=args.logfile, level=logging_level)

    base_dir = args.datadir
    subdir = 'GEOSIT_alpha_4' if args.ceres else 'GEOSIT'

    ts = pd.to_datetime(args.datetime)
    band_upper = args.band.upper()

    def build_path(species):
        fname = (
            f"GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24."
            f"GEOS5294.{species}_{band_upper}.{ts.strftime('%Y-%m-%dT%H00')}.V01.nc4"
        )
        return os.path.join(base_dir, subdir, ts.strftime('%Y'),
                            ts.strftime('%m'), fname)

    file_a = build_path(args.species_a)
    file_b = build_path(args.species_b)

    for f in (file_a, file_b):
        if not os.path.isfile(f):
            logging.error('File not found: %s', f)
            sys.exit(1)

    try:
        os.makedirs(args.outdir, exist_ok=True)
        outdir = args.outdir
    except PermissionError:
        fallback_outdir = os.path.join(os.getcwd(), 'Plots')
        logging.warning('Could not write to %s, using %s',
                        args.outdir, fallback_outdir)
        os.makedirs(fallback_outdir, exist_ok=True)
        outdir = fallback_outdir

    plotfile = os.path.join(
        outdir,
        f"{args.species_a}_minus_{args.species_b}_{band_upper}_{ts.strftime('%Y%m%dT%H')}"
    )

    process_diff(args.band, args.species_a, args.species_b,
                 file_a, file_b, plotfile)
