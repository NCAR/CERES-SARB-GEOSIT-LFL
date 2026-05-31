"""Source dispatch table for the GEOS-IT / MERRA-2 input paths.

Each Source entry knows the source-specific filename conventions, time-
stepping cadence, and path construction rules. The science modules
(species_optics.py, external_mix.py) import get_source() and delegate
all source-specific string manipulation to the returned Source.
"""

import os
from dataclasses import dataclass
from typing import Callable
from utils import fill_date_hour_template, find_file


@dataclass(frozen=True)
class Source:
    name: str
    default_file_pattern: str
    cadence: str                          # pd.date_range freq: '3h' or 'D'
    output_subdir: str                    # e.g. 'GEOSIT_alpha_4'
    aer_filename_glob_suffix: str         # for run_daily_processing skip-check
    aer_filename_template: str            # for check_aer_grid
    species_glob_pattern: str             # for external_mix default --file_pattern
    resolve_input: Callable               # (datadir, pattern, date) -> str
    build_output_name: Callable           # (input_path, datadir, outdir, date, t,
                                          #  species_label, band_label) -> str


def _date_to_template_str(date):
    """Convert a pd.Timestamp to the dash-separated string accepted by
    fill_date_hour_template: YYYY-MM-MABBR-DD-DDD-HH."""
    return date.strftime('%Y-%m-%b-%d-%j-%H')


def _geosit_resolve_input(datadir, pattern, date):
    return os.path.join(datadir,
        fill_date_hour_template(pattern, _date_to_template_str(date)))


def _geosit_build_output_name(input_path, datadir, outdir, date, t,
                               species_label, band_label):
    # Mirror today's species_optics.py logic at lines 454-463 + 283-293,
    # collapsed into one function. The `t` argument is unused for GEOS-IT
    # because the timestep is already encoded in the input filename
    # (one file per 3h timestep); it's accepted for signature compatibility
    # with the MERRA-2 builder.
    del t  # unused for GEOS-IT
    del date  # unused for GEOS-IT
    rel = os.path.relpath(input_path, datadir)
    rel_out = rel.replace('GEOSIT/', 'GEOSIT_alpha_4/', 1)
    filename_out = os.path.join(outdir, rel_out)
    filename_labeled = filename_out.replace(
        'GEOS5294.', f'GEOS5294.{species_label}_{band_label}.')
    return filename_labeled.replace('L576x361_v72', 'L288x180_v24')


def _merra2_resolve_input(datadir, pattern, date):
    # MERRA-2 files are daily; pattern contains a wildcard for the
    # stream prefix (MERRA2_100/200/300/400 by year). utils.find_file
    # globs and requires exactly one match — fails fast on ambiguity.
    filestr = fill_date_hour_template(pattern, _date_to_template_str(date))
    return find_file(datadir, filestr)


def _merra2_build_output_name(input_path, datadir, outdir, date, t,
                               species_label, band_label):
    # One MERRA-2 daily input → eight per-timestep outputs. HH = 3 * t.
    del input_path  # not needed; output path is synthesized from date+t
    del datadir
    year = date.strftime('%Y')
    month = date.strftime('%m')
    day = date.strftime('%Y-%m-%d')
    hh = '%02d' % (3 * t)
    return os.path.join(outdir,
        'MERRA2_alpha_4', year, month,
        f'MERRA2.aer_inst_3hr_glo_L288x180_v24.'
        f'{species_label}_{band_label}.{day}T{hh}00.nc4')


SOURCES: dict[str, Source] = {}

SOURCES['geosit'] = Source(
    name='geosit',
    default_file_pattern=(
        'GEOSIT/YYYY/MM/'
        'GEOS.it.asm.aer_inst_3hr_glo_L576x361_v72.GEOS5294.'
        'YYYY-MM-DDTHH00.V01.nc4'),
    cadence='3h',
    output_subdir='GEOSIT_alpha_4',
    aer_filename_glob_suffix='.{date}T*.V01.nc4',
    aer_filename_template=(
        'GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.'
        'AER_{band}.{date}{ts}.V01.nc4'),
    species_glob_pattern=(
        'GEOSIT_alpha_4/YYYY/MM/'
        'GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.'
        '*_band.YYYY-MM-DDTHH00.V01.nc4'),
    resolve_input=_geosit_resolve_input,
    build_output_name=_geosit_build_output_name,
)

SOURCES['merra2'] = Source(
    name='merra2',
    default_file_pattern=(
        'MERRA2/YYYY/MM/MERRA2_*.inst3_3d_aer_Nv.YYYYMMDD.nc4'),
    cadence='D',
    output_subdir='MERRA2_alpha_4',
    aer_filename_glob_suffix='.{date}T*.nc4',
    aer_filename_template=(
        'MERRA2.aer_inst_3hr_glo_L288x180_v24.'
        'AER_{band}.{date}{ts}.nc4'),
    species_glob_pattern=(
        'MERRA2_alpha_4/YYYY/MM/'
        'MERRA2.aer_inst_3hr_glo_L288x180_v24.'
        '*_band.YYYY-MM-DDTHH00.nc4'),
    resolve_input=_merra2_resolve_input,
    build_output_name=_merra2_build_output_name,
)


def get_source(name: str) -> Source:
    if name not in SOURCES:
        valid = ', '.join(sorted(SOURCES.keys()))
        raise ValueError(
            f"unknown source {name!r}; valid sources: {valid}")
    return SOURCES[name]
