import os
import sys
import argparse
import logging
import numpy as np
import pandas as pd
import xarray as xr
from pprint import pprint
import cartopy
from plots import plot_lon_lat

mpl_dir = os.path.join('/tmp', 'matplotlib')
os.makedirs(mpl_dir, exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR', mpl_dir)

cartopy_data_dir = os.path.join('/tmp', 'cartopy')
os.makedirs(cartopy_data_dir, exist_ok=True)
cartopy.config['data_dir'] = cartopy_data_dir

plot_params = dict()
# Plot params will be filled dynamically per-field


def _compute_levels(field_values):
    vmax = float(np.nanmax(field_values))
    if not np.isfinite(vmax) or vmax <= 0:
        return np.linspace(0, 1, 11)
    # Cap plotted range at 1.0 and use 0.05 steps
    capped = min(vmax, 1.0)
    base_step = 0.05
    upper = np.ceil(capped / base_step) * base_step
    upper = min(upper, 1.0)
    levels = np.arange(0, upper + base_step * 0.5, base_step)
    # Finer low-end resolution
    augment = [lvl for lvl in (0.005, 0.01, 0.02, 0.03, 0.04)
               if lvl < base_step and lvl < upper]
    if augment:
        levels = np.unique(np.concatenate([levels, augment]))
        levels.sort()
    return levels


def process_file(band, species, filename, plotfile):

    logging.info('Opening ' + filename)

    ds = xr.open_dataset(filename)

    pprint(ds)

    field = ds['Extinction_Column_Optical_Depth']
    levels = _compute_levels(field.values)
    plot_params_local = {
        'levels': levels,
        'augment_levels': []  # already baked into levels
    }

    title = 'GEOSIT ' + species + ' AOD ' + band.upper()

    plot_lon_lat(plotfile, title,
        {**plot_params_local, 'coastlines': True}, field,
        symmetric=False)

if __name__ == '__main__':

    """
    Parse command line arguments
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--logfile', type=str,
        default=sys.stdout,
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
    parser.add_argument('--species', type=str, default='AER',
        help='species code (e.g., AER for total, SO4, NO3AN1, etc.)')
    parser.add_argument('--datetime', type=str,
        default='2010-01-01T00',
        help='datetime for file selection (YYYY-MM-DDTHH)')
    parser.add_argument('--ceres', action='store_true',
        help='use CERES production paths (/CERES/sarb/dfillmor/GEOSIT_alpha_4)')
    args = parser.parse_args()

    """
    Setup logging
    """
    logging_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(stream=args.logfile, level=logging_level)

    base_dir = args.datadir
    subdir = 'GEOSIT_alpha_4' if args.ceres else 'GEOSIT'

    ts = pd.to_datetime(args.datetime)
    band_upper = args.band.upper()
    fname = (
        f"GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24."
        f"GEOS5294.{args.species}_{band_upper}.{ts.strftime('%Y-%m-%dT%H00')}.V01.nc4"
    )
    filename = os.path.join(base_dir, subdir, ts.strftime('%Y'), ts.strftime('%m'), fname)

    try:
        os.makedirs(args.outdir, exist_ok=True)
        outdir = args.outdir
    except PermissionError:
        fallback_outdir = os.path.join(os.getcwd(), 'Plots')
        logging.warning('Could not write to %s, using %s', args.outdir, fallback_outdir)
        os.makedirs(fallback_outdir, exist_ok=True)
        outdir = fallback_outdir

    plotfile = os.path.join(
        outdir,
        f"{args.species}_{band_upper}_{ts.strftime('%Y%m%dT%H')}"
    )

    if not os.path.isfile(filename):
        logging.error('File not found: %s', filename)
        sys.exit(1)

    process_file(args.band, args.species, filename, plotfile)
