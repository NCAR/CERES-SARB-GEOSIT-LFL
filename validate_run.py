import os
import sys
import argparse
from datetime import datetime
import pandas as pd


SPECIES_NO_BIN = [
    'SO4', 'OCPHOBIC', 'OCPHILIC', 'BCPHOBIC', 'BCPHILIC', 'NO3AN1'
]
SPECIES_WITH_BIN = [f'SS{n:03d}' for n in range(1, 6)] \
    + [f'DU{n:03d}' for n in range(1, 6)]
ALL_SPECIES = SPECIES_NO_BIN + SPECIES_WITH_BIN

SW_BANDS = [f'SW{n:02d}' for n in range(1, 15)]
LW_BANDS = [f'LW{n:02d}' for n in range(1, 13)]
ALL_BANDS = SW_BANDS + LW_BANDS

FILE_PATTERN = os.path.join(
    'GEOSIT', 'YYYY', 'MM',
    'GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.'
    '{label}_{band}.YYYY-MM-DDTHH00.V01.nc4')


def build_file_list(datadir, file_pattern, dates, species, bands,
                    include_species=True, include_aer=True):
    """Build complete list of expected file paths."""
    paths = []
    for date in dates:
        date_str = date.strftime('%Y-%m-%b-%d-%j-%H')
        yyyy, mm, _, dd, _, hh = date_str.split('-')
        for band in bands:
            if include_species:
                for sp in species:
                    p = file_pattern.replace('YYYY', yyyy) \
                        .replace('MM', mm).replace('DD', dd) \
                        .replace('HH', hh) \
                        .replace('{label}', sp).replace('{band}', band)
                    paths.append(os.path.join(datadir, p))
            if include_aer:
                p = file_pattern.replace('YYYY', yyyy) \
                    .replace('MM', mm).replace('DD', dd) \
                    .replace('HH', hh) \
                    .replace('{label}', 'AER').replace('{band}', band)
                paths.append(os.path.join(datadir, p))
    return paths


def check_files(paths):
    """Check each path for existence and non-zero size.

    Returns (found, missing, zero_size) as lists of paths.
    """
    found, missing, zero_size = [], [], []
    for p in paths:
        if not os.path.exists(p):
            missing.append(p)
        elif os.path.getsize(p) == 0:
            zero_size.append(p)
        else:
            found.append(p)
    return found, missing, zero_size


def main():
    parser = argparse.ArgumentParser(
        description='Validate output files from a GEOSIT-LFL processing run')
    parser.add_argument('--start', type=str, default='2010-01-01',
        help='start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default='2010-01-01',
        help='end date (YYYY-MM-DD, inclusive)')
    parser.add_argument('--datadir', type=str,
        default=os.path.join(os.getenv('HOME'), 'Data'),
        help='top-level data directory (default $HOME/Data)')
    parser.add_argument('--ceres', action='store_true',
        help='use CERES production paths (/CERES/sarb/dfillmor/GEOSIT_alpha_4)')
    parser.add_argument('--species-only', action='store_true',
        help='only check species files (skip AER)')
    parser.add_argument('--aer-only', action='store_true',
        help='only check AER aggregate files (skip species)')
    parser.add_argument('--dry-run', action='store_true',
        help='print expected file list without checking disk')
    args = parser.parse_args()

    if args.species_only and args.aer_only:
        parser.error('--species-only and --aer-only are mutually exclusive')

    file_pattern = FILE_PATTERN
    datadir = args.datadir

    if args.ceres:
        datadir = '/CERES/sarb/dfillmor/'
        file_pattern = file_pattern.replace('GEOSIT/', 'GEOSIT_alpha_4/')

    include_species = not args.aer_only
    include_aer = not args.species_only

    # Build date range covering all 3-hourly timesteps through end of last day
    end_last_hour = args.end + 'T21'
    start_first_hour = args.start + 'T00'
    dates = pd.date_range(start=start_first_hour, end=end_last_hour, freq='3h')

    paths = build_file_list(datadir, file_pattern, dates, ALL_SPECIES,
                            ALL_BANDS, include_species, include_aer)

    if args.dry_run:
        for p in paths:
            print(p)
        print(f'\nTotal expected files: {len(paths)}')
        return

    # Check files and report per-day summaries
    all_missing = []
    all_zero = []
    day_groups = {}
    for p in paths:
        # Extract date from path (YYYY-MM-DDTHH00)
        basename = os.path.basename(p)
        date_part = basename.split('.')[-2]  # YYYY-MM-DDTHH00
        day = date_part[:10]  # YYYY-MM-DD
        day_groups.setdefault(day, []).append(p)

    print(f'{"Date":<12} {"Expected":>8} {"Found":>8} {"Missing":>8} {"Zero-size":>10}')
    print('-' * 50)

    for day in sorted(day_groups):
        day_paths = day_groups[day]
        found, missing, zero_size = check_files(day_paths)
        all_missing.extend(missing)
        all_zero.extend(zero_size)
        status = '  OK' if not missing and not zero_size else '  **'
        print(f'{day:<12} {len(day_paths):>8} {len(found):>8} '
              f'{len(missing):>8} {len(zero_size):>10}{status}')

    print('-' * 50)
    total = len(paths)
    total_ok = total - len(all_missing) - len(all_zero)
    print(f'{"TOTAL":<12} {total:>8} {total_ok:>8} '
          f'{len(all_missing):>8} {len(all_zero):>10}')

    if all_missing or all_zero:
        # Write full list to log file
        log_path = 'validate_run.log'
        with open(log_path, 'w') as f:
            for p in all_missing:
                f.write(f'MISSING  {p}\n')
            for p in all_zero:
                f.write(f'ZERO     {p}\n')
        print(f'\nFull list written to {log_path}')
        sys.exit(1)
    else:
        print('\nAll files present and non-empty.')
        sys.exit(0)


if __name__ == '__main__':
    main()
