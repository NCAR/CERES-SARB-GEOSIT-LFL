import os
import sys
import argparse
import logging
import yaml
import numpy as np
import pandas as pd
import xarray as xr
from datetime import datetime, UTC
from pprint import pprint
from scipy.interpolate import interp1d

from utils import fill_date_hour_template

np.set_printoptions(threshold=np.inf)

tau_thresh = 0.00001

"""
v0.1 Initial Version
v0.2 Added vertical summing and latitude averaging for subsampled output
"""

__version__ = 'v0.2'

g_earth = 9.8

species_map = {'SU': 'SO4',
               'OCPHO': 'OCPHOBIC',
               'OCPHI': 'OCPHILIC',
               'BCPHO': 'BCPHOBIC',
               'BCPHI': 'BCPHILIC',
               'SS': 'SS',
               'DU': 'DU',
               'NI': 'NO3AN'}


def rh_interp(ds_coarse):
    # pprint(ds_coarse)
    rh_coarse = ds_coarse.rh
    rh_fine = np.arange(0, 1, 0.01)
    nrh = len(rh_fine)

    ext_coarse = ds_coarse.bext
    sca_coarse = ds_coarse.bsca
    asm_coarse = ds_coarse.g
    shape_coarse = ext_coarse.shape
    shape_fine = (shape_coarse[0], nrh, shape_coarse[2])
    ext_fine = np.zeros(shape_fine)
    sca_fine = np.zeros(shape_fine)
    asm_fine = np.zeros(shape_fine)

    for r in range(shape_coarse[0]):
        for k in range(shape_coarse[2]):
            f_ext = interp1d(rh_coarse, ext_coarse[r,:,k],
                kind='linear', fill_value='extrapolate')
            f_sca = interp1d(rh_coarse, sca_coarse[r,:,k],
                kind='linear', fill_value='extrapolate')
            f_asm = interp1d(rh_coarse, asm_coarse[r,:,k],
                kind='linear', fill_value='extrapolate')
            ext_fine[r,:,k] = f_ext(rh_fine)
            sca_fine[r,:,k] = f_sca(rh_fine)
            asm_fine[r,:,k] = f_asm(rh_fine)

    dims_fine = ext_coarse.dims
    da_ext = xr.DataArray(ext_fine, dims=dims_fine)
    da_sca = xr.DataArray(sca_fine, dims=dims_fine)
    da_asm = xr.DataArray(asm_fine, dims=dims_fine)

    return xr.Dataset({'ext': da_ext, 'sca': da_sca, 'asm': da_asm},
            coords={'lambda': ds_coarse.coords['lambda']})


def read_aerosol_optics(filename, species, band):

    logging.info(filename)
    with open(args.aerosol, 'r') as f:
        aerosol_config = yaml.safe_load(f)
        # pprint(aerosol_config)

    file_optics = os.path.expandvars(
        aerosol_config['Types'][species]['filename'])
    # Prefer MERRA2 optics; fall back to band-specific GEOSIT if present
    geosit_optics = file_optics.replace('MERRA2',
        'GEOSIT_' + band.upper())
    if not os.path.exists(file_optics) and os.path.exists(geosit_optics):
        logging.info('MERRA2 optics missing; using %s', geosit_optics)
        file_optics = geosit_optics
    logging.debug(file_optics)
    ds_optics = xr.open_dataset(file_optics)
    ds_optics_interp = rh_interp(ds_optics)
    ds_optics_interp.to_netcdf(
        file_optics.replace('.nc', '_interp.nc'))

    bands_file = os.path.expandvars(aerosol_config['filename_bands'])
    logging.debug('bands file: %s', bands_file)
    ds_bands = xr.open_dataset(bands_file)

    return ds_optics_interp, ds_bands


def process_file(filename, filename_out,
    ds_optics, species, size_bin, band,
    wvl_min, wvl_max, idx_wvl):

    date_str = filename.split('.')[2]

    logging.info(filename)
    print(filename)
    print(filename_out)
    ds = xr.open_dataset(filename)
    ntime, nlev, nlat, nlon = ds['RH'].shape
    # print(ntime, nlev, nlat, nlon)
    # (time: 8, lev: 72, lat: 361, lon: 576)

    """
    bext  (radius, rh, lambda)
    dtau_s = alpha_s dz
    alpha_s = rho_s k_s = rho q_s k_s
    rho dz = - dp / g
    dtau_s = q_s k_s dp / g
    """

    if species == 'SS' or species == 'DU':
        species += size_bin
        idx_size = int(size_bin) - 1
    elif species == 'NO3AN':
        # Nitrate only uses the first size bin
        species = 'NO3AN1'
        idx_size = 0
    else:
        idx_size = 0

    tau_thresh = 0.00001

    for t in range(ntime):

        utc_time = datetime.now(UTC)
        utc_time_str = datetime.strftime(utc_time, '%Y/%m/%d_%H:%M:%S')

        logging.info(ds['time'].values[t])

        rh = ds['RH'].values[t,:,:,:].flatten()
        if 'PHO' in species:
            idx_rh = np.zeros(len(rh), dtype=np.int32)
        else:
            idx_rh = np.array(np.floor(rh * 100), dtype=np.int32)
            idx_rh[idx_rh > 99] = 99

        delp = ds['DELP'].values[t,:,:,:].flatten()

        q_species = ds[species].values[t,:,:,:].flatten()

        k_ext = ds_optics['ext'].values[idx_size, idx_rh, idx_wvl]
        k_sca = ds_optics['sca'].values[idx_size, idx_rh, idx_wvl]
        asm = ds_optics['asm'].values[idx_size, idx_rh, idx_wvl]

        tau_ext = delp * q_species * k_ext / g_earth
        tau_sca = delp * q_species * k_sca / g_earth

        da_delp = xr.DataArray(
            delp.reshape(nlev, nlat, nlon).astype(np.float32),
            dims=['lev', 'lat', 'lon'])
        da_tau_ext = xr.DataArray(
            tau_ext.reshape(nlev, nlat, nlon).astype(np.float32),
            dims=['lev', 'lat', 'lon'])
        da_tau_sca = xr.DataArray(
            tau_sca.reshape(nlev, nlat, nlon).astype(np.float32),
            dims=['lev', 'lat', 'lon'])
        da_asm = xr.DataArray(
            asm.reshape(nlev, nlat, nlon).astype(np.float32),
            dims=['lev', 'lat', 'lon'])

        da_tau_ext_column = da_tau_ext.sum(dim='lev')

        lat_mid = 0.5 * (ds.coords['lat'].values[:-1]
                + ds.coords['lat'].values[1:])
        lat_sub = 0.5 * (lat_mid[:-1:2] + lat_mid[1::2])

        delp_mid = 0.5 * (da_delp.values[:,:-1,:] + da_delp.values[:,1:,:])
        delp_sub = np.zeros((nlev // 3, nlat // 2, nlon // 2), dtype=np.float32)

        tau_ext_mid = 0.5 * (da_tau_ext.values[:,:-1,:] + da_tau_ext.values[:,1:,:])
        tau_ext_sub = np.zeros((nlev // 3, nlat // 2, nlon // 2), dtype=np.float32)

        tau_sca_mid = 0.5 * (da_tau_sca.values[:,:-1,:] + da_tau_sca.values[:,1:,:])
        tau_sca_sub = np.zeros((nlev // 3, nlat // 2, nlon // 2), dtype=np.float32)

        asm_mid = 0.5 * (da_asm.values[:,:-1,:] + da_asm.values[:,1:,:])
        asm_sub = np.zeros((nlev // 3, nlat // 2, nlon // 2), dtype=np.float32)

        for ilev in range(nlev // 3):
            ilev_start = 3 * ilev
            delp_sub[ilev,:,:] \
                = 0.5 * (delp_mid[ilev_start:ilev_start+3,:-1:2,::2].sum(axis=0)
                + delp_mid[ilev_start:ilev_start+3,1::2,::2].sum(axis=0))

            tau_ext_sub[ilev,:,:] \
                = 0.5 * (tau_ext_mid[ilev_start:ilev_start+3,:-1:2,::2].sum(axis=0)
                + tau_ext_mid[ilev_start:ilev_start+3,1::2,::2].sum(axis=0))

            tau_sca_sub[ilev,:,:] \
                = 0.5 * (tau_sca_mid[ilev_start:ilev_start+3,:-1:2,::2].sum(axis=0)
                + tau_sca_mid[ilev_start:ilev_start+3,1::2,::2].sum(axis=0))

            asm_sub[ilev,:,:] \
                = 0.5 * (asm_mid[ilev_start:ilev_start+3,:-1:2,::2].mean(axis=0)
                + asm_mid[ilev_start:ilev_start+3,1::2,::2].mean(axis=0))

        tau_ext_sub = np.clip(tau_ext_sub, 0, 10)
        tau_sca_sub = np.clip(tau_sca_sub, 0, tau_ext_sub)
        asm_sub = np.clip(asm_sub, -1, 1)

        da_lat_sub = xr.DataArray(lat_sub, dims=['lat']).astype(np.float32)
        da_lat_sub.attrs['long_name'] = 'latitude'
        da_lat_sub.attrs['units'] = 'degrees_north'

        da_delp_sub = xr.DataArray(delp_sub,
            dims=['lev', 'lat', 'lon'])
        da_tau_ext_sub = xr.DataArray(tau_ext_sub,
            dims=['lev', 'lat', 'lon'])
        da_tau_sca_sub = xr.DataArray(tau_sca_sub,
            dims=['lev', 'lat', 'lon'])
        da_asm_sub = xr.DataArray(asm_sub,
            dims=['lev', 'lat', 'lon'])

        da_tau_ext_sub_column = da_tau_ext_sub.sum(dim='lev')

        print('AOD Global Mean %.3f' % da_tau_ext_column.mean())

        """
        Output
        """
        ds.coords['lat'].values[nlat // 2] = 0.0
        ds_out = xr.Dataset({
            'PS': ds['PS'][t,:,:],
            'DELP': ds['DELP'][t,:,:,:],
            'Extinction_Layer_Optical_Depth': da_tau_ext,
            'Scattering_Layer_Optical_Depth': da_tau_sca,
            'Layer_Asymmetry_Parameter': da_asm,
            'Extinction_Column_Optical_Depth': da_tau_ext_column},
            coords = {'lat': ds.coords['lat'].astype(np.float32),
                      'lon': ds.coords['lon'].astype(np.float32)})
        ds_out.attrs['datetime'] = date_str + ('_%.2dZ' % (3 * t))
        ds_out.attrs['input_filename'] = filename
        ds_out.attrs['processing_datetime'] = utc_time_str
        ds_out.attrs['Langley_Fu_Liou_band'] = band.upper()
        ds_out.attrs['band_wvl_min_micron'] = wvl_min
        ds_out.attrs['band_wvl_max_micron'] = wvl_max
        ds_out.attrs['script_version'] \
            = os.path.join(os.getcwd(), 'species_optics.py ') \
            + __version__
        filename_labeled_out \
            = filename_out.replace('GEOS5294.',
                'GEOS5294.' + species + '_' + band.upper() + '.')
                # '_%.2dZ.nc' % (3 * t)).replace('Nv.',
                # 'Nv.' + species + '_' + band.upper() + '.')
        # logging.info('writing:' + filename_labeled_out)
        # ds_out.to_netcdf(filename_labeled_out)
        # print(filename_labeled_out)

        filename_subsampled_out \
            = filename_labeled_out.replace('L576x361_v72', 'L288x180_v24')
            # = filename_labeled_out.replace('Nv', 'Nv_180x288L24')
        ds_sub_out = xr.Dataset({
            'DELP': da_delp_sub,
            'Extinction_Layer_Optical_Depth': da_tau_ext_sub,
            'Scattering_Layer_Optical_Depth': da_tau_sca_sub,
            'Layer_Asymmetry_Parameter': da_asm_sub,
            'Extinction_Column_Optical_Depth': da_tau_ext_sub_column},
            coords = {'lat': da_lat_sub,
                      'lon': ds.coords['lon'][::2].astype(np.float32)})
        ds_sub_out.attrs['datetime'] = date_str + ('_%.2dZ' % (3 * t))
        ds_sub_out.attrs['input_filename'] = filename
        ds_sub_out.attrs['processing_datetime'] = utc_time_str
        ds_sub_out.attrs['Langley_Fu_Liou_band'] = band.upper()
        ds_sub_out.attrs['band_wvl_min_micron'] = wvl_min
        ds_sub_out.attrs['band_wvl_max_micron'] = wvl_max
        ds_sub_out.attrs['script_version'] \
            = os.path.join(os.getcwd(), 'species_optics.py ') \
            + __version__
        ds_sub_out.to_netcdf(filename_subsampled_out)
        print(filename_subsampled_out)


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
        default='/CERES/sarb/dfillmor/',
        help='top-level output directory (default $HOME/Data/Output)')
    parser.add_argument('--aerosol', type=str,
        default=os.path.join('aerosol.yaml'),
        help='yaml aerosol file')
    parser.add_argument('--species', type=str,
        default=os.path.join('SU'),
        help='aerosol species')
    parser.add_argument('--size_bin', type=str,
        default=os.path.join('001'),
        help='aerosol size bin')
    parser.add_argument('--band', type=str, default='sw01')
    parser.add_argument('--start', type=str,
        default='2010-01-01T00',
        help='start datetime (YYYY-MM-DDTHH)')
    parser.add_argument('--end', type=str,
        default='2010-01-01T00',
        help='end datetime (YYYY-MM-DDTHH)')
    geos_it_filestr = \
        'GEOS.it.asm.aer_inst_3hr_glo_L576x361_v72.GEOS5294.YYYY-MM-DDTHH00.V01.nc4'
    parser.add_argument('--file_pattern', type=str,
        default=os.path.join('GEOSIT', 'YYYY', 'MM', geos_it_filestr))
        # default=os.path.join('MERRA2', 'YYYY', 'MM',
        #     'MERRA2_300.inst3_3d_aer_Nv.YYYYMMDD.nc4'))
    parser.add_argument('--ceres', action='store_true',
        help='use CERES production paths and aerosol_ceres.yaml')
    args = parser.parse_args()

    if os.path.isdir(args.datadir):
        logging.info(args.datadir)
    else:
        args.datadir = os.path.join(os.getenv('HOME'), 'Data')

    if os.path.isdir(args.outdir):
        logging.info(args.outdir)
    else:
        args.outdir = os.path.join(os.getenv('HOME'), 'Data', 'Output')

    if args.ceres:
        # Point to production aerosol config and paths
        args.aerosol = 'aerosol_ceres.yaml'
        args.datadir = '/CERES_prd/GMAO/'
        args.outdir = '/CERES/sarb/dfillmor/'
        args.file_pattern = os.path.join('GEOSIT', 'YYYY', 'MM', geos_it_filestr)

    """
    Setup logging
    """
    logging_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(stream=args.logfile, level=logging_level)

    ds_optics, ds_bands \
        = read_aerosol_optics(args.aerosol, args.species, args.band)

    wvls = ds_optics.coords['lambda'].values * 1.0e6
    nwvl = len(wvls)
    # print(wvls)
    # 1 0.3 um, 5 0.5 um, 8 0.65 um, 12 0.9 um

    # get band wavelength
    band_idx = int(args.band[2:4])
    logging.info('band_idx:%d' % band_idx)
    if 'sw' in args.band:
        wvl_max = ds_bands['LFL_SW_bands'].values[band_idx]
        wvl_min = ds_bands['LFL_SW_bands'].values[band_idx - 1]
    if 'lw' in args.band:
        wvl_max = ds_bands['LFL_LW_bands'].values[band_idx]
        wvl_min = ds_bands['LFL_LW_bands'].values[band_idx - 1]
    wvl_band = 0.5 * (wvl_max + wvl_min)
    logging.info('wavelength:%.2f' % wvl_band)

    idx_wvl = np.argmin(np.abs(wvls - wvl_band))
    logging.info('wavelength:%.2f\n' % wvls[idx_wvl])

    # dates = pd.date_range(start=args.start, end=args.end, freq='D')
    dates = pd.date_range(start=args.start, end=args.end, freq='3h')
    logging.info(dates)
    print(dates)

    for date in dates:
        date_str = date.strftime('%Y-%m-%b-%d-%j-%H')
        filename = os.path.join(args.datadir,
            fill_date_hour_template(args.file_pattern, date_str))
        filename_out = filename.replace('/CERES_prd/GMAO/GEOSIT',
            '/CERES/sarb/dfillmor/GEOSIT_alpha_4')
        process_file(filename, filename_out, ds_optics,
            species_map[args.species], args.size_bin, args.band,
            wvl_min, wvl_max, idx_wvl)
