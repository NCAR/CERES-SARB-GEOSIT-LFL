"""Source dispatch table for the GEOS-IT / MERRA-2 input paths.

Each Source entry knows the source-specific filename conventions, time-
stepping cadence, and path construction rules. The science modules
(species_optics.py, external_mix.py) import get_source() and delegate
all source-specific string manipulation to the returned Source.
"""

from dataclasses import dataclass
from typing import Callable


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


SOURCES: dict[str, Source] = {}


def get_source(name: str) -> Source:
    if name not in SOURCES:
        valid = ', '.join(sorted(SOURCES.keys()))
        raise ValueError(
            f"unknown source {name!r}; valid sources: {valid}")
    return SOURCES[name]
