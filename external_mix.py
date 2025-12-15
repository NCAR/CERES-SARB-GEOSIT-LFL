import os
import sys
import argparse
import logging
from datetime import datetime, UTC
from glob import glob
from pprint import pprint
import numpy as np
import pandas as pd
import xarray as xr

from utils import fill_date_hour_template

np.set_printoptions(threshold=np.inf)


__version__ = 'v0.2'

# Species lists (includes nitrate and size-binned species)
# Use actual output file species names; allow aliases for convenience.
SPECIES_NO_BIN = [
    'SO4', 'OCPHOBIC', 'OCPHILIC', 'BCPHOBIC', 'BCPHILIC', 'NO3AN1'
]
SPECIES_WITH_BIN = [f'SS{n:03d}' for n in range(1, 6)] \
    + [f'DU{n:03d}' for n in range(1, 6)]
ALL_SPECIES = SPECIES_NO_BIN + SPECIES_WITH_BIN

SPECIES_ALIAS = {
    'SU': 'SO4',
    'OCPHO': 'OCPHOBIC',
    'OCPHI': 'OCPHILIC',
    'BCPHO': 'BCPHOBIC',
    'BCPHI': 'BCPHILIC',
    'NI': 'NO3AN1',
}


def process_file(pattern, species_list):

    tau_thresh = 0.00001

    utc_time = datetime.now(UTC)
    utc_time_str = datetime.strftime(utc_time, '%Y/%m/%d_%H:%M:%S')

    logging.info(pattern)

    files = []
    for species in species_list:
        species_actual = SPECIES_ALIAS.get(species, species)
        species_pattern = pattern.replace('*_', f'{species_actual}_')
        matched = sorted(glob(species_pattern))
        # Drop any preexisting AER totals from consideration
        matched = [m for m in matched if '_AER_' not in m]
        if not matched:
            # Try legacy path by swapping GEOSIT to GEOSIT_alpha_4
            legacy_pattern = species_pattern.replace('GEOSIT/', 'GEOSIT_alpha_4/')
            legacy_matched = sorted(glob(legacy_pattern))
            legacy_matched = [m for m in legacy_matched if '_AER_' not in m]
            matched = legacy_matched
            if matched:
                logging.warning('Using legacy path for %s', legacy_pattern)
        if not matched:
            logging.warning('No files matched for %s', species_pattern)
        else:
            files.extend(matched)

    if len(files) == 0:
        logging.warning('No files matched pattern %s (or legacy); skipping', pattern)
        return

    filename_out = pattern.replace('*_', 'AER_')

    ds_out = xr.open_dataset(files[0])
    ds_out.attrs['input_filename'] = str(files)
    ds_out.attrs['processing_datetime'] = utc_time_str
    ds_out.attrs['script_version'] \
        = os.path.join(os.getcwd(), 'external_mix.py ') \
        + __version__

    ds_out['Extinction_Layer_Optical_Depth'].values[:] = 0.0
    ds_out['Scattering_Layer_Optical_Depth'].values[:] = 0.0
    ds_out['Layer_Asymmetry_Parameter'].values[:] = 0.0
    ds_out['Extinction_Column_Optical_Depth'].values[:] = 0.0

    pprint(ds_out)

    n_types = 0

    for filename in files:
        logging.info(filename)
        ds = xr.open_dataset(filename)

        n_types += 1

        ds_out['Extinction_Layer_Optical_Depth'].values[:] \
            += ds['Extinction_Layer_Optical_Depth'].values[:]
        ds_out['Scattering_Layer_Optical_Depth'].values[:] \
            += ds['Scattering_Layer_Optical_Depth'].values[:]
        ds_out['Extinction_Column_Optical_Depth'].values[:] \
            += ds['Extinction_Column_Optical_Depth'].values[:]
        ds_out['Layer_Asymmetry_Parameter'].values[:] \
            += ds['Scattering_Layer_Optical_Depth'].values[:] \
             * ds['Layer_Asymmetry_Parameter'].values[:]

    print('Total AOD Global Mean %.3f' % ds_out['Extinction_Column_Optical_Depth'].values[:].mean())

    mask = (ds_out['Scattering_Layer_Optical_Depth'].values[:] \
        <= tau_thresh)
    ds_out['Layer_Asymmetry_Parameter'].values[mask] = 0.0

    mask = (ds_out['Scattering_Layer_Optical_Depth'].values[:] \
        > tau_thresh)
    ds_out['Layer_Asymmetry_Parameter'].values[mask] \
        /= ds_out['Scattering_Layer_Optical_Depth'].values[mask]

    logging.info(filename_out)
    ds_out.to_netcdf(filename_out)


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
        help='top-level data directory')
    parser.add_argument('--start', type=str,
        default='2010-01-01T00',
        help='start datetime (YYYY-MM-DDTHH)')
    parser.add_argument('--end', type=str,
        default='2010-01-01T00',
        help='end datetime (YYYY-MM-DDTHH)')
    parser.add_argument('--file_pattern', type=str,
        default=os.path.join('GEOSIT', 'YYYY', 'MM',
            'GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.*_band.YYYY-MM-DDTHH00.V01.nc4'))
    parser.add_argument('--band', type=str, default='sw01')
    parser.add_argument('--species', nargs='*', default=ALL_SPECIES,
        help='species to include (defaults to all)')
    parser.add_argument('--ceres', action='store_true',
        help='use CERES production paths (/CERES/sarb/dfillmor/GEOSIT_alpha_4)')
    args = parser.parse_args()

    if args.ceres:
        args.datadir = '/CERES/sarb/dfillmor/'
        args.file_pattern = args.file_pattern.replace('GEOSIT/', 'GEOSIT_alpha_4/')

    """
    Setup logging
    """
    logging_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(stream=args.logfile, level=logging_level)

    dates = pd.date_range(start=args.start, end=args.end, freq='3h')
    logging.info(dates)

    for date in dates:
        date_str = date.strftime('%Y-%m-%b-%d-%j-%H')
        logging.info(date_str)
        filename = os.path.join(args.datadir,
            fill_date_hour_template(args.file_pattern, date_str))
        filename = filename.replace('band', args.band.upper())
        process_file(filename, args.species)
