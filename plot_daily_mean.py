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


TIMESTAMPS_INST = ['T0000', 'T0300', 'T0600', 'T0900', 'T1200', 'T1500', 'T1800', 'T2100']
TIMESTAMPS_TAVG = ['T0130', 'T0430', 'T0730', 'T1030', 'T1330', 'T1630', 'T1930', 'T2230']


def regrid_to_subsampled(field_native, lat_native, lon_native):
    """Regrid a 2D (361x576) field to the subsampled (180x288) grid.

    Matches the subsampling in species_optics.py:
      lat: midpoints of adjacent pairs (361->360), then average pairs (360->180)
      lon: every other point (576->288)
    """
    # lat: midpoints then pair-average
    field_mid = 0.5 * (field_native[:-1, :] + field_native[1:, :])  # (360, 576)
    field_sub = 0.5 * (field_mid[:-1:2, :] + field_mid[1::2, :])    # (180, 576)
    # lon: every other point
    field_sub = field_sub[:, ::2]                                     # (180, 288)

    lat_mid = 0.5 * (lat_native[:-1] + lat_native[1:])
    lat_sub = 0.5 * (lat_mid[:-1:2] + lat_mid[1::2])
    lon_sub = lon_native[::2]

    return field_sub, lat_sub, lon_sub


def load_totexttau_daily_mean(datadir, date):
    """Load all 8 tavg slv TOTEXTTAU files and return the daily mean on the subsampled grid."""
    fields = []
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
        fields.append(ds['TOTEXTTAU'].values[0, :, :])  # (361, 576)
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


def load_daily_mean(datadir, date, species, band):
    """Load all 8 3-hourly files for a species/band and return the daily mean dataset."""
    datasets = []
    band_upper = band.upper()
    for ts in TIMESTAMPS_INST:
        fname = (
            f"GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24."
            f"GEOS5294.{species}_{band_upper}.{date}{ts}.V01.nc4"
        )
        fpath = os.path.join(datadir, 'GEOSIT', date[:4], date[5:7], fname)
        if not os.path.isfile(fpath):
            logging.warning('Missing file: %s', fpath)
            continue
        datasets.append(xr.open_dataset(fpath))
    if not datasets:
        return None
    # Average Extinction_Column_Optical_Depth across all timestamps
    aod_stack = np.stack([ds['Extinction_Column_Optical_Depth'].values for ds in datasets])
    aod_mean = aod_stack.mean(axis=0)
    ds0 = datasets[0]
    da_mean = xr.DataArray(aod_mean, dims=['lat', 'lon'],
                           coords={'lat': ds0.coords['lat'], 'lon': ds0.coords['lon']})
    return da_mean


def plot_species(datadir, outdir, date, species, band, label=None):
    """Compute daily mean and plot for one species."""
    da = load_daily_mean(datadir, date, species, band)
    if da is None:
        logging.error('No data for %s %s', species, band)
        return
    if label is None:
        label = species
    levels = _compute_levels(da.values)
    plot_params = {
        'levels': levels,
        'augment_levels': [],
        'coastlines': True,
    }
    title = f'GEOSIT {label} Daily Mean AOD {band.upper()} {date}'
    plotfile = os.path.join(outdir, f'{label}_daily_mean_{band.upper()}_{date.replace("-", "")}')
    logging.info('Plotting %s -> %s', title, plotfile)
    plot_lon_lat(plotfile, title, plot_params, da, symmetric=False)
    print(f'  Wrote {plotfile}.png  (mean={float(da.mean()):.4f})')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Plot daily mean AOD from 3-hourly files')
    parser.add_argument('--datadir', type=str, default=os.path.join(os.getenv('HOME'), 'Data'))
    parser.add_argument('--outdir', type=str, default=os.path.join(os.getenv('HOME'), 'Plots'))
    parser.add_argument('--date', type=str, default='2008-07-01')
    parser.add_argument('--band', type=str, default='sw05')
    parser.add_argument('--species', nargs='*', default=None,
                        help='species to plot (default: AER + major groups)')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    os.makedirs(args.outdir, exist_ok=True)

    if args.species:
        species_list = [(s, s) for s in args.species]
    else:
        # Default: total AER + major species groups
        species_list = [
            ('AER', 'AER (Total)'),
            ('SO4', 'Sulfate'),
            ('DU001', 'Dust bin1'),
            ('DU002', 'Dust bin2'),
            ('DU003', 'Dust bin3'),
            ('DU004', 'Dust bin4'),
            ('DU005', 'Dust bin5'),
            ('SS001', 'Sea Salt bin1'),
            ('SS002', 'Sea Salt bin2'),
            ('BCPHILIC', 'BC Philic'),
            ('BCPHOBIC', 'BC Phobic'),
            ('OCPHILIC', 'OC Philic'),
            ('OCPHOBIC', 'OC Phobic'),
            ('NO3AN1', 'Nitrate bin1'),
        ]

    for species_code, label in species_list:
        plot_species(args.datadir, args.outdir, args.date, species_code, args.band, label=label)

    # --- AER vs TOTEXTTAU diff plot ---
    da_aer = load_daily_mean(args.datadir, args.date, 'AER', args.band)
    da_tot = load_totexttau_daily_mean(args.datadir, args.date)
    if da_aer is not None and da_tot is not None:
        diff = da_aer - da_tot
        # Use 99th percentile to set scale (avoid outlier blow-up)
        p99 = float(np.nanpercentile(np.abs(diff.values), 99))
        vmax = max(np.ceil(p99 * 100) / 100, 0.01)  # round up to nearest 0.01
        levels = np.linspace(-vmax, vmax, 21)
        plot_params = {
            'levels': levels,
            'augment_levels': [],
            'coastlines': True,
        }
        title = (f'GEOSIT AER - TOTEXTTAU Daily Mean AOD '
                 f'{args.band.upper()} {args.date}')
        plotfile = os.path.join(
            args.outdir,
            f'AER_minus_TOTEXTTAU_daily_mean_{args.band.upper()}_{args.date.replace("-", "")}')
        plot_lon_lat(plotfile, title, plot_params, diff, symmetric=True)
        print(f'  Wrote {plotfile}.png')
        print(f'    AER mean={float(da_aer.mean()):.4f}  '
              f'TOTEXTTAU mean={float(da_tot.mean()):.4f}  '
              f'diff mean={float(diff.mean()):.4f}')

        # Relative difference: (AER - TOTEXTTAU) / TOTEXTTAU * 100
        rel_diff = xr.where(da_tot > 0.01, diff / da_tot * 100, np.nan)
        rel_p99 = float(np.nanpercentile(np.abs(rel_diff.values), 99))
        rel_vmax = max(np.ceil(rel_p99 / 5) * 5, 5)  # round up to nearest 5%
        rel_levels = np.linspace(-rel_vmax, rel_vmax, 21)
        rel_params = {
            'levels': rel_levels,
            'augment_levels': [],
            'coastlines': True,
        }
        title_rel = (f'GEOSIT (AER - TOTEXTTAU) / TOTEXTTAU [%] '
                     f'{args.band.upper()} {args.date}')
        plotfile_rel = os.path.join(
            args.outdir,
            f'AER_minus_TOTEXTTAU_reldiff_{args.band.upper()}_{args.date.replace("-", "")}')
        plot_lon_lat(plotfile_rel, title_rel, rel_params, rel_diff, symmetric=True)
        print(f'  Wrote {plotfile_rel}.png')

        # Also plot TOTEXTTAU itself for reference
        levels_tot = _compute_levels(da_tot.values)
        plot_params_tot = {
            'levels': levels_tot,
            'augment_levels': [],
            'coastlines': True,
        }
        title_tot = f'GEOSIT TOTEXTTAU Daily Mean AOD 550nm {args.date}'
        plotfile_tot = os.path.join(
            args.outdir,
            f'TOTEXTTAU_daily_mean_{args.date.replace("-", "")}')
        plot_lon_lat(plotfile_tot, title_tot, plot_params_tot, da_tot, symmetric=False)
        print(f'  Wrote {plotfile_tot}.png  (mean={float(da_tot.mean()):.4f})')
