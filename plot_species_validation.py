import os
import sys
import argparse
import logging
import numpy as np
import xarray as xr
import cartopy

mpl_dir = os.path.join('/tmp', 'matplotlib')
os.makedirs(mpl_dir, exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR', mpl_dir)

cartopy_data_dir = os.path.join('/tmp', 'cartopy')
os.makedirs(cartopy_data_dir, exist_ok=True)
cartopy.config['data_dir'] = cartopy_data_dir

from plots import plot_lon_lat
from plot_geosit import _compute_levels
from plot_daily_mean import load_daily_mean, regrid_to_subsampled, TIMESTAMPS_TAVG


SPECIES_GROUPS = {
    'Sulfate':       {'native_var': 'SUEXTTAU',  'species': ['SO4']},
    'Dust':          {'native_var': 'DUEXTTAU',  'species': ['DU001', 'DU002', 'DU003', 'DU004', 'DU005']},
    'SeaSalt':       {'native_var': 'SSEXTTAU',  'species': ['SS001', 'SS002', 'SS003', 'SS004', 'SS005']},
    'BlackCarbon':   {'native_var': 'BCEXTTAU',  'species': ['BCPHILIC', 'BCPHOBIC']},
    'OrganicCarbon': {'native_var': 'OCEXTTAU',  'species': ['OCPHILIC', 'OCPHOBIC']},
    'Nitrate':       {'native_var': 'NIEXTTAU',  'species': ['NO3AN1', 'NO3AN2', 'NO3AN3']},
    'Total':         {'native_var': 'TOTEXTTAU', 'species': ['AER']},
}


def load_native_exttau_daily_mean(datadir, date, varname):
    """Load all 8 tavg slv files for a native EXTTAU variable and return daily mean on subsampled grid."""
    fields = []
    lat_native = lon_native = None
    for ts in TIMESTAMPS_TAVG:
        fname = (
            f"GEOS.it.asm.aer_tavg_3hr_glo_L576x361_slv."
            f"GEOS5294.{date}{ts}.V01.nc4"
        )
        fpath = os.path.join(datadir, 'GEOSIT', date[:4], date[5:7], fname)
        if not os.path.isfile(fpath):
            logging.warning('Missing tavg file: %s', fpath)
            continue
        ds = xr.open_dataset(fpath)
        fields.append(ds[varname].values[0, :, :])  # (361, 576)
        lat_native = ds.coords['lat'].values
        lon_native = ds.coords['lon'].values
    if not fields:
        return None
    native_mean = np.stack(fields).mean(axis=0)
    field_sub, lat_sub, lon_sub = regrid_to_subsampled(native_mean, lat_native, lon_native)
    da = xr.DataArray(field_sub.astype(np.float32), dims=['lat', 'lon'],
                      coords={'lat': lat_sub.astype(np.float32),
                              'lon': lon_sub.astype(np.float32)})
    return da


def validate_species(datadir, outdir, date, band, group_name, group_config, subdir='GEOSIT', diff_scale=None):
    """Produce validation plots for one species group: native, computed, diff, reldiff."""
    native_var = group_config['native_var']
    species_list = group_config['species']
    date_compact = date.replace('-', '')
    band_upper = band.upper()

    # Load native AOD
    da_native = load_native_exttau_daily_mean(datadir, date, native_var)
    if da_native is None:
        logging.error('No native data for %s (%s)', group_name, native_var)
        return

    # Load and sum computed species AOD
    da_computed = None
    for sp in species_list:
        da_sp = load_daily_mean(datadir, date, sp, band, subdir=subdir)
        if da_sp is None:
            logging.error('No computed data for %s', sp)
            return
        da_computed = da_sp if da_computed is None else da_computed + da_sp

    # 1. Native AOD map
    levels = _compute_levels(da_native.values)
    plot_params = {'levels': levels, 'augment_levels': [], 'coastlines': True}
    title = f'GEOSIT {native_var} Daily Mean AOD 550nm {date}'
    plotfile = os.path.join(outdir, f'{group_name}_native_{band_upper}_{date_compact}')
    plot_lon_lat(plotfile, title, plot_params, da_native, symmetric=False)
    print(f'  Wrote {plotfile}.png  (mean={float(da_native.mean()):.4f})')

    # 2. Computed AOD map
    levels = _compute_levels(da_computed.values)
    plot_params = {'levels': levels, 'augment_levels': [], 'coastlines': True}
    sp_label = '+'.join(species_list)
    title = f'GEOSIT {sp_label} Daily Mean AOD {band_upper} {date}'
    plotfile = os.path.join(outdir, f'{group_name}_computed_{band_upper}_{date_compact}')
    plot_lon_lat(plotfile, title, plot_params, da_computed, symmetric=False)
    print(f'  Wrote {plotfile}.png  (mean={float(da_computed.mean()):.4f})')

    # 3. Absolute difference
    diff = da_computed - da_native
    if diff_scale is not None:
        vmax = diff_scale
    else:
        p99 = float(np.nanpercentile(np.abs(diff.values), 99))
        vmax = max(np.ceil(p99 * 100) / 100, 0.01)
    levels = np.linspace(-vmax, vmax, 21)
    plot_params = {'levels': levels, 'augment_levels': [], 'coastlines': True}
    title = f'GEOSIT {sp_label} - {native_var} {band_upper} {date}'
    plotfile = os.path.join(outdir, f'{group_name}_diff_{band_upper}_{date_compact}')
    plot_lon_lat(plotfile, title, plot_params, diff, symmetric=True)
    print(f'  Wrote {plotfile}.png')

    # 4. Relative difference (masked where native < 0.01)
    rel_diff = xr.where(da_native > 0.01, diff / da_native * 100, np.nan)
    rel_p99 = float(np.nanpercentile(np.abs(rel_diff.values), 99))
    rel_vmax = max(np.ceil(rel_p99 / 5) * 5, 5)
    rel_levels = np.linspace(-rel_vmax, rel_vmax, 21)
    rel_params = {'levels': rel_levels, 'augment_levels': [], 'coastlines': True}
    title = f'GEOSIT ({sp_label} - {native_var}) / {native_var} [%] {band_upper} {date}'
    plotfile = os.path.join(outdir, f'{group_name}_reldiff_{band_upper}_{date_compact}')
    plot_lon_lat(plotfile, title, rel_params, rel_diff, symmetric=True)
    print(f'  Wrote {plotfile}.png')

    # Summary stats
    print(f'  {group_name}: native mean={float(da_native.mean()):.4f}  '
          f'computed mean={float(da_computed.mean()):.4f}  '
          f'diff mean={float(diff.mean()):.4f}  '
          f'diff std={float(diff.std()):.4f}  '
          f'diff max={float(np.nanmax(np.abs(diff.values))):.4f}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Per-species AOD validation: computed vs native GEOS-IT diagnostics')
    parser.add_argument('--datadir', type=str, default=os.path.join(os.getenv('HOME'), 'Data'))
    parser.add_argument('--outdir', type=str, default=os.path.join(os.getenv('HOME'), 'Plots'))
    parser.add_argument('--date', type=str, default='2008-07-01')
    parser.add_argument('--band', type=str, default='sw05')
    parser.add_argument('--species', nargs='*', default=None,
                        help='species groups to validate (default: all)')
    parser.add_argument('--diff_scale', type=float, default=None,
                        help='fixed vmax for absolute diff plots (default: auto per species)')
    parser.add_argument('--ceres', action='store_true',
                        help='use CERES production paths (GEOSIT_alpha_4)')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    os.makedirs(args.outdir, exist_ok=True)

    subdir = 'GEOSIT_alpha_4' if args.ceres else 'GEOSIT'

    if args.species:
        groups = {k: v for k, v in SPECIES_GROUPS.items() if k in args.species}
        if not groups:
            logging.error('No matching species groups. Available: %s',
                          list(SPECIES_GROUPS.keys()))
            sys.exit(1)
    else:
        groups = SPECIES_GROUPS

    for group_name, group_config in groups.items():
        print(f'\n=== {group_name} ===')
        validate_species(args.datadir, args.outdir, args.date, args.band,
                         group_name, group_config, subdir=subdir,
                         diff_scale=args.diff_scale)
