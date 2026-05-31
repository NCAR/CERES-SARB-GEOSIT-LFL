# MERRA-2 input support for species_optics + external_mix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add permanent `--source merra2` input support to `species_optics.py` and `external_mix.py` (alongside the existing GEOS-IT path), so production runs can use MERRA-2 `inst3_3d_aer_Nv` daily files as a first-class input source. GEOS-IT runs stay byte-identical.

**Architecture:** A new `sources.py` module holds a `Source` dataclass and a `SOURCES['geosit'|'merra2']` dispatch table. Each entry knows its default file pattern, time-stepping cadence (`'3h'` vs `'D'`), output subdir, AER filename templates, and two callables: `resolve_input` (build/glob the input path for a date) and `build_output_name` (build the per-timestep output path). `species_optics.py` and `external_mix.py` import `get_source(args.source)` and delegate all source-specific logic to it. The science (RH indexing, k_ext, tau_ext, subsampling) is untouched.

**Tech Stack:** Python 3 stdlib + numpy + xarray (already in the `sarb` conda env). New module is pure stdlib. Tests are stdlib `unittest`, invoked with `python -m unittest` — no pytest dependency.

**Spec:** `docs/superpowers/specs/2026-05-30-merra2-input-support-design.md`

**Branch:** All work lands on the `merra2` branch (already created from `main` at commit `f41c13e`, which holds the spec).

**Testing approach:** This repo has no test framework today. We add `tests/test_sources.py` for the new `sources.py` module — pure string-in / string-out, runs in <1s via `python -m unittest tests.test_sources`. For the script edits to `species_optics.py`/`external_mix.py`/`check_aer_grid.py`/the shell wrappers, we lean on the existing manual-verification pattern used in prior plans: REPL sanity checks for argparse, and **byte-identical output for a known GEOS-IT day** as the regression net. The MERRA-2 path itself is validated by a smoke test at the end.

**Reference data for regression checks:**
- GEOS-IT golden day: `/CERES/sarb/dfillmor/GEOSIT_alpha_4/2008/07/` (already populated). Use `--start 2008-07-01T00 --end 2008-07-01T00` (one timestep) for fastest regression checks.
- MERRA-2 smoke day: `/CERES_prd/GMAO/MERRA2/2008/07/MERRA2_300.inst3_3d_aer_Nv.20080701.nc4` (confirmed present).

---

### Task 1: Switch to the `merra2` branch

All subsequent commits go on this branch.

**Files:** None (git state only).

- [ ] **Step 1: Confirm starting state**

Run:
```bash
git status --short
git branch --show-current
```

Expected: branch is `main`, working tree clean (apart from pre-existing untracked `RUN`, `logs/`, `qc/`, and the unstaged `CLAUDE.md` deletion — leave all of these alone).

- [ ] **Step 2: Switch to merra2**

Run:
```bash
git switch merra2
git log -1 --oneline
```

Expected last commit: `f41c13e Spec: MERRA-2 input support for species_optics + external_mix`. (The branch was created from this commit, so it already contains the spec.)

- [ ] **Step 3: No commit needed**

This task is operational only.

---

### Task 2: Create `sources.py` skeleton + tests directory

Foundation: the `Source` dataclass and `get_source()` lookup with a clear error on unknown sources. Both `SOURCES` entries are added empty for now — populated in Tasks 3 and 4.

**Files:**
- Create: `sources.py`
- Create: `tests/__init__.py` (empty)
- Create: `tests/test_sources.py`

- [ ] **Step 1: Write the failing test**

Create `tests/__init__.py` (empty file — makes `tests` a package so `python -m unittest tests.test_sources` works):

```bash
mkdir -p tests
: > tests/__init__.py
```

Create `tests/test_sources.py`:

```python
import unittest

from sources import Source, SOURCES, get_source


class TestGetSource(unittest.TestCase):

    def test_get_source_geosit_returns_source(self):
        src = get_source('geosit')
        self.assertIsInstance(src, Source)
        self.assertEqual(src.name, 'geosit')

    def test_get_source_merra2_returns_source(self):
        src = get_source('merra2')
        self.assertIsInstance(src, Source)
        self.assertEqual(src.name, 'merra2')

    def test_unknown_source_raises_with_valid_options(self):
        with self.assertRaises(ValueError) as cx:
            get_source('geosfp')
        msg = str(cx.exception)
        self.assertIn('geosfp', msg)
        self.assertIn('geosit', msg)
        self.assertIn('merra2', msg)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python -m unittest tests.test_sources -v
```

Expected: `ImportError: cannot import name 'Source' from 'sources'` (or `ModuleNotFoundError: No module named 'sources'`).

- [ ] **Step 3: Write minimal `sources.py`**

Create `sources.py`:

```python
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
```

- [ ] **Step 4: Run test — first two will still fail, third should pass**

Run:
```bash
python -m unittest tests.test_sources -v
```

Expected: `test_unknown_source_raises_with_valid_options` is the only one passing — but it will fail because `SOURCES` is empty so the message won't contain `geosit` or `merra2`. That's expected; Tasks 3-4 fix it.

Specifically:
- `test_get_source_geosit_returns_source` — FAIL (`unknown source 'geosit'`)
- `test_get_source_merra2_returns_source` — FAIL (`unknown source 'merra2'`)
- `test_unknown_source_raises_with_valid_options` — FAIL (`'geosit' not found in message` because SOURCES is empty)

This is the "red" state of TDD — Tasks 3 and 4 will turn it green.

- [ ] **Step 5: Commit**

```bash
git add sources.py tests/__init__.py tests/test_sources.py
git commit -m "sources: Source dataclass + get_source() skeleton"
```

---

### Task 3: Add `SOURCES['geosit']` entry

Encodes today's GEOS-IT behavior verbatim. The `build_output_name` callable must produce strings byte-identical to today's `.replace(...)` chain in `species_optics.py:283-293` — the test in Step 1 pins this.

**Files:**
- Modify: `sources.py` — add `_geosit_resolve_input`, `_geosit_build_output_name`, and the `SOURCES['geosit']` entry.
- Modify: `tests/test_sources.py` — add `TestGeositSource`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sources.py`:

```python
import os
import pandas as pd


class TestGeositSource(unittest.TestCase):

    def setUp(self):
        self.src = get_source('geosit')

    def test_fields_match_today_constants(self):
        self.assertEqual(self.src.name, 'geosit')
        self.assertEqual(self.src.cadence, '3h')
        self.assertEqual(self.src.output_subdir, 'GEOSIT_alpha_4')
        self.assertEqual(
            self.src.default_file_pattern,
            'GEOSIT/YYYY/MM/'
            'GEOS.it.asm.aer_inst_3hr_glo_L576x361_v72.GEOS5294.'
            'YYYY-MM-DDTHH00.V01.nc4')
        self.assertEqual(
            self.src.aer_filename_glob_suffix, '.{date}T*.V01.nc4')
        self.assertEqual(
            self.src.aer_filename_template,
            'GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.'
            'AER_{band}.{date}{ts}.V01.nc4')
        self.assertEqual(
            self.src.species_glob_pattern,
            'GEOSIT_alpha_4/YYYY/MM/'
            'GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.'
            '*_band.YYYY-MM-DDTHH00.V01.nc4')

    def test_resolve_input_builds_exact_path(self):
        # date 2008-07-01 03Z under /CERES_prd/GMAO/ with the default pattern
        date = pd.Timestamp('2008-07-01T03')
        path = self.src.resolve_input(
            '/CERES_prd/GMAO/',
            self.src.default_file_pattern,
            date)
        self.assertEqual(
            path,
            '/CERES_prd/GMAO/GEOSIT/2008/07/'
            'GEOS.it.asm.aer_inst_3hr_glo_L576x361_v72.GEOS5294.'
            '2008-07-01T0300.V01.nc4')

    def test_build_output_name_matches_today_replace_chain(self):
        # Reproduce today's species_optics.py output filename for
        # (species_label='SO4', band_label='SW01', t=0) given a GEOS-IT
        # input path under /CERES_prd/GMAO/ and outdir /CERES/sarb/dfillmor/.
        # Today's logic (species_optics.py:454-463 + :283-293):
        #   rel       = os.path.relpath(filename, datadir)
        #   rel_out   = rel.replace('GEOSIT/', 'GEOSIT_alpha_4/', 1)
        #   filename_out = os.path.join(outdir, rel_out)
        #   filename_labeled_out = filename_out.replace(
        #       'GEOS5294.', 'GEOS5294.SO4_SW01.')
        #   filename_subsampled_out = filename_labeled_out.replace(
        #       'L576x361_v72', 'L288x180_v24')
        input_path = ('/CERES_prd/GMAO/GEOSIT/2008/07/'
            'GEOS.it.asm.aer_inst_3hr_glo_L576x361_v72.GEOS5294.'
            '2008-07-01T0000.V01.nc4')
        date = pd.Timestamp('2008-07-01T00')
        expected = ('/CERES/sarb/dfillmor/GEOSIT_alpha_4/2008/07/'
            'GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.'
            'SO4_SW01.2008-07-01T0000.V01.nc4')
        got = self.src.build_output_name(
            input_path=input_path,
            datadir='/CERES_prd/GMAO/',
            outdir='/CERES/sarb/dfillmor/',
            date=date,
            t=0,
            species_label='SO4',
            band_label='SW01')
        self.assertEqual(got, expected)
```

Run:
```bash
python -m unittest tests.test_sources.TestGeositSource -v
```

Expected: all three fail with `unknown source 'geosit'` (SOURCES still empty).

- [ ] **Step 2: Implement the GEOS-IT entry in `sources.py`**

Add to `sources.py` (after the `get_source` function — but registry entries must be defined before `get_source` calls. Easiest: add helpers and registry-mutation BEFORE the closing of the module, and let `get_source` see the populated dict at import time):

Add these helpers above the `SOURCES: dict[...]` line:

```python
import os
from utils import fill_date_hour_template


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
```

Then below the `SOURCES: dict[...] = {}` line, populate it:

```python
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
```

- [ ] **Step 3: Run tests — geosit tests should now pass**

Run:
```bash
python -m unittest tests.test_sources -v
```

Expected:
- `TestGetSource.test_get_source_geosit_returns_source` — PASS
- `TestGetSource.test_get_source_merra2_returns_source` — FAIL (merra2 still missing)
- `TestGetSource.test_unknown_source_raises_with_valid_options` — FAIL (message lacks `merra2`)
- `TestGeositSource.test_fields_match_today_constants` — PASS
- `TestGeositSource.test_resolve_input_builds_exact_path` — PASS
- `TestGeositSource.test_build_output_name_matches_today_replace_chain` — PASS

- [ ] **Step 4: Commit**

```bash
git add sources.py tests/test_sources.py
git commit -m "sources: add SOURCES['geosit'] entry with byte-identical GEOS-IT logic"
```

---

### Task 4: Add `SOURCES['merra2']` entry

The new path. Output filename is synthesized per timestep (HH = 3*t) under `MERRA2_alpha_4/YYYY/MM/`. Input is resolved via `utils.find_file` which globs `MERRA2_*` and requires exactly one match.

**Files:**
- Modify: `sources.py` — add `_merra2_resolve_input`, `_merra2_build_output_name`, and the `SOURCES['merra2']` entry.
- Modify: `tests/test_sources.py` — add `TestMerra2Source`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sources.py`:

```python
from unittest.mock import patch


class TestMerra2Source(unittest.TestCase):

    def setUp(self):
        self.src = get_source('merra2')

    def test_fields_match_spec(self):
        self.assertEqual(self.src.name, 'merra2')
        self.assertEqual(self.src.cadence, 'D')
        self.assertEqual(self.src.output_subdir, 'MERRA2_alpha_4')
        self.assertEqual(
            self.src.default_file_pattern,
            'MERRA2/YYYY/MM/MERRA2_*.inst3_3d_aer_Nv.YYYYMMDD.nc4')
        self.assertEqual(
            self.src.aer_filename_glob_suffix, '.{date}T*.nc4')
        self.assertEqual(
            self.src.aer_filename_template,
            'MERRA2.aer_inst_3hr_glo_L288x180_v24.'
            'AER_{band}.{date}{ts}.nc4')
        self.assertEqual(
            self.src.species_glob_pattern,
            'MERRA2_alpha_4/YYYY/MM/'
            'MERRA2.aer_inst_3hr_glo_L288x180_v24.'
            '*_band.YYYY-MM-DDTHH00.nc4')

    def test_resolve_input_globs_stream_prefix(self):
        # Confirm the pattern handed to find_file contains MERRA2_*
        # (not a hardcoded stream number) and that the year/month/day
        # substitutions are applied before globbing.
        captured = {}
        def fake_find_file(datadir, filestr):
            captured['datadir'] = datadir
            captured['filestr'] = filestr
            return os.path.join(datadir, filestr).replace(
                'MERRA2_*', 'MERRA2_300')
        with patch('sources.find_file', side_effect=fake_find_file):
            date = pd.Timestamp('2008-07-01T00')
            path = self.src.resolve_input(
                '/CERES_prd/GMAO/',
                self.src.default_file_pattern,
                date)
        self.assertEqual(captured['datadir'], '/CERES_prd/GMAO/')
        self.assertEqual(
            captured['filestr'],
            'MERRA2/2008/07/MERRA2_*.inst3_3d_aer_Nv.20080701.nc4')
        self.assertEqual(
            path,
            '/CERES_prd/GMAO/MERRA2/2008/07/'
            'MERRA2_300.inst3_3d_aer_Nv.20080701.nc4')

    def test_build_output_name_eight_timesteps(self):
        # For t=0..7, the HH in the filename should be 00,03,06,...,21.
        input_path = ('/CERES_prd/GMAO/MERRA2/2008/07/'
            'MERRA2_300.inst3_3d_aer_Nv.20080701.nc4')
        date = pd.Timestamp('2008-07-01T00')
        expected_hh = ['0000', '0300', '0600', '0900',
                       '1200', '1500', '1800', '2100']
        for t, hh in enumerate(expected_hh):
            got = self.src.build_output_name(
                input_path=input_path,
                datadir='/CERES_prd/GMAO/',
                outdir='/CERES/sarb/dfillmor/',
                date=date,
                t=t,
                species_label='SO4',
                band_label='SW01')
            expected = ('/CERES/sarb/dfillmor/MERRA2_alpha_4/2008/07/'
                'MERRA2.aer_inst_3hr_glo_L288x180_v24.'
                f'SO4_SW01.2008-07-01T{hh}.nc4')
            self.assertEqual(got, expected, f't={t}')
```

Run:
```bash
python -m unittest tests.test_sources.TestMerra2Source -v
```

Expected: all three fail with `unknown source 'merra2'`.

- [ ] **Step 2: Implement the MERRA-2 entry**

In `sources.py`, change the top-level import to add `find_file`:

```python
from utils import fill_date_hour_template, find_file
```

Add the merra2 helpers above `SOURCES: dict[...] = {}` (after the geosit helpers from Task 3):

```python
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
```

Add the registry entry below the geosit one:

```python
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
```

**Note on `fill_date_hour_template` and the MERRA-2 pattern:** the template handles `YYYY`, `MM`, `M_ABBR`, `DD`, `HH` substitutions but NOT `YYYYMMDD` as a single token. Inspect `utils.py:22-37` — it operates by chained `.replace()`, so `YYYYMMDD` becomes `<yyyy><mm><dd>` after the three individual substitutions land. That works as-is. Verify in Step 3.

- [ ] **Step 3: Run tests — all should pass**

Run:
```bash
python -m unittest tests.test_sources -v
```

Expected: all 9 tests PASS. If `test_resolve_input_globs_stream_prefix` fails because the captured `filestr` is something other than `MERRA2/2008/07/MERRA2_*.inst3_3d_aer_Nv.20080701.nc4`, inspect what `fill_date_hour_template` did to `YYYYMMDD` and adjust the helper accordingly.

- [ ] **Step 4: Commit**

```bash
git add sources.py tests/test_sources.py
git commit -m "sources: add SOURCES['merra2'] entry with daily-file dispatch"
```

---

### Task 5: Wire `species_optics.py` to the source dispatch

The biggest single edit. Three things happen here:
1. Add `--source` argparse flag; default `--file_pattern` becomes `None`.
2. Drop the `--ceres` block's hardcoded `args.file_pattern = ...GEOSIT...` override.
3. Refactor: open the dataset and run the `for t in range(ntime)` loop in the main date loop (not inside `process_file`); rename `process_file` to `process_file_one_timestep` and remove the per-timestep `.replace(...)` filename construction.

**Files:**
- Modify: `species_optics.py` — argparse (~line 322-371), `--ceres` block (~line 383-388), refactor `process_file` (lines 125-313), date loop (lines 449-463).

- [ ] **Step 1: Add `--source` argparse flag and switch `--file_pattern` default to None**

In `species_optics.py` argparse block (lines 322-371), make these changes.

Find this block (around line 355):

```python
    parser.add_argument('--file_pattern', type=str,
        default=os.path.join('GEOSIT', 'YYYY', 'MM', geos_it_filestr))
        # default=os.path.join('MERRA2', 'YYYY', 'MM',
        #     'MERRA2_300.inst3_3d_aer_Nv.YYYYMMDD.nc4'))
```

Replace with:

```python
    parser.add_argument('--file_pattern', type=str, default=None,
        help='input file pattern under --datadir; defaults to the '
             '--source default (see sources.py)')
    parser.add_argument('--source', choices=['geosit', 'merra2'],
        default='geosit',
        help='input data source: geosit (3-hourly files) or '
             'merra2 (daily files)')
```

(`geos_it_filestr` is still used as a local literal; leave its declaration on line 353-354 alone — it's referenced by the now-removed `--ceres` override line, which we'll delete in Step 2. After Step 2, the local variable becomes unused and can be deleted in Step 3.)

- [ ] **Step 2: Drop the `--ceres` file_pattern override**

Find this block (lines 383-388):

```python
    if args.ceres:
        # Point to production aerosol config and paths
        args.aerosol = 'aerosol_ceres.yaml'
        args.datadir = '/CERES_prd/GMAO/'
        args.outdir = '/CERES/sarb/dfillmor/'
        args.file_pattern = os.path.join('GEOSIT', 'YYYY', 'MM', geos_it_filestr)
```

Replace with:

```python
    if args.ceres:
        # Point to production aerosol config and paths. The file pattern
        # comes from sources.get_source(args.source) below — not hardcoded.
        args.aerosol = 'aerosol_ceres.yaml'
        args.datadir = '/CERES_prd/GMAO/'
        args.outdir = '/CERES/sarb/dfillmor/'
```

- [ ] **Step 3: Remove the now-unused `geos_it_filestr` local**

Find this block (lines 353-354):

```python
    geos_it_filestr = \
        'GEOS.it.asm.aer_inst_3hr_glo_L576x361_v72.GEOS5294.YYYY-MM-DDTHH00.V01.nc4'
```

Delete those two lines. They were only referenced by `--file_pattern`'s old default and the `--ceres` override, both gone.

- [ ] **Step 4: Refactor `process_file` → `process_file_one_timestep`**

In `species_optics.py`, find the function definition at line 125:

```python
def process_file(filename, filename_out,
    ds_optics, species, size_bin, band_label,
    wvl_min, wvl_max, idx_wvl):

    date_str = filename.split('.')[2]

    logging.info(filename)
    print(filename)
    print(filename_out)
    ds = xr.open_dataset(filename)
    ntime, nlev, nlat, nlon = ds['RH'].shape
```

Replace with:

```python
def process_file_one_timestep(input_path, output_path, ds, t,
    ds_optics, species, size_bin, band_label,
    wvl_min, wvl_max, idx_wvl, date):

    date_str = date.strftime('%Y%m%d')

    logging.info(input_path)
    print(input_path)
    print(output_path)
    ntime, nlev, nlat, nlon = ds['RH'].shape
```

Now delete the `for t in range(ntime):` loop indentation. Find this line (around line 166):

```python
    for t in range(ntime):

        utc_time = datetime.now(UTC)
```

Replace with (note: removed the loop, kept its body at one less indent level):

```python
    utc_time = datetime.now(UTC)
```

Then de-indent the entire body of the former `for t in range(ntime):` loop (lines 167-313 in the original file) by one level. The body ends at the final `print(filename_subsampled_out)` (originally line 313).

**Inside the de-indented body**, change the output-filename construction. Find this block (originally around lines 283-293, but now de-indented):

```python
        filename_labeled_out \
            = filename_out.replace('GEOS5294.',
                'GEOS5294.' + species_label + '_' + band_label + '.')
                # '_%.2dZ.nc' % (3 * t)).replace('Nv.',
                # 'Nv.' + species + '_' + band.upper() + '.')
        # logging.info('writing:' + filename_labeled_out)
        # ds_out.to_netcdf(filename_labeled_out)
        # print(filename_labeled_out)

        filename_subsampled_out \
            = filename_labeled_out.replace('L576x361_v72', 'L288x180_v24')
            # = filename_labeled_out.replace('Nv', 'Nv_180x288L24')
```

Replace with:

```python
    # output_path is built source-aware by Source.build_output_name in the caller.
    filename_subsampled_out = output_path
```

(After de-indent, this single line replaces the entire former filename-construction block.)

Then near the end of the function, find:

```python
        ds_sub_out.to_netcdf(filename_subsampled_out)
        print(filename_subsampled_out)
```

These stay as-is (already de-indented now). No change.

Also update the input_filename attrs lines — find both (around lines 275 and 304 originally):

```python
        ds_out.attrs['input_filename'] = filename
```

Replace with (note: `filename` is no longer a local — use `input_path`):

```python
    ds_out.attrs['input_filename'] = input_path
```

Same for `ds_sub_out.attrs['input_filename'] = filename` → `ds_sub_out.attrs['input_filename'] = input_path`.

- [ ] **Step 5: Update the main date loop**

In `species_optics.py`, find this block (lines 449-463):

```python
    # dates = pd.date_range(start=args.start, end=args.end, freq='D')
    dates = pd.date_range(start=args.start, end=args.end, freq='3h')
    logging.info(dates)
    print(dates)

    for date in dates:
        date_str = date.strftime('%Y-%m-%b-%d-%j-%H')
        filename = os.path.join(args.datadir,
            fill_date_hour_template(args.file_pattern, date_str))
        rel = os.path.relpath(filename, args.datadir)
        rel_out = rel.replace('GEOSIT/', 'GEOSIT_alpha_4/', 1)
        filename_out = os.path.join(args.outdir, rel_out)
        process_file(filename, filename_out, ds_optics,
            species_map[args.species], args.size_bin, band_label,
            wvl_min, wvl_max, idx_wvl)
```

Replace with:

```python
    src = get_source(args.source)
    if args.file_pattern is None:
        args.file_pattern = src.default_file_pattern
    dates = pd.date_range(start=args.start, end=args.end, freq=src.cadence)
    logging.info(dates)
    print(dates)

    for date in dates:
        input_path = src.resolve_input(args.datadir, args.file_pattern, date)
        ds = xr.open_dataset(input_path)
        ntime = ds['RH'].shape[0]
        species_actual = species_map[args.species]

        # Build species_label for filename — matches today's process_file
        # internal logic (lines 147-162 of the original). Note the
        # asymmetric padding: SS/DU keep 3-digit bin ('SS001'), NO3AN
        # uses 1-digit ('NO3AN1'). This matches external_mix.py:26 which
        # defines SPECIES_WITH_BIN with the same format.
        if species_actual in ('SS', 'DU'):
            species_label = species_actual + args.size_bin
        elif species_actual == 'NO3AN':
            species_label = species_actual + str(int(args.size_bin))
        else:
            species_label = species_actual

        for t in range(ntime):
            output_path = src.build_output_name(
                input_path=input_path,
                datadir=args.datadir,
                outdir=args.outdir,
                date=date,
                t=t,
                species_label=species_label,
                band_label=band_label)
            process_file_one_timestep(
                input_path=input_path,
                output_path=output_path,
                ds=ds,
                t=t,
                ds_optics=ds_optics,
                species=species_actual,
                size_bin=args.size_bin,
                band_label=band_label,
                wvl_min=wvl_min,
                wvl_max=wvl_max,
                idx_wvl=idx_wvl,
                date=date)
        ds.close()
```

**Note on species_label duplication:** the same species_label-building logic now lives both in the caller (above) AND inside `process_file_one_timestep` (the original lines 147-162 are still in the function body for index computation: `idx_size = int(size_bin) - 1` etc.). The caller's copy is only used for filename construction; the function's copy is only used for array indexing. They are intentionally separate — the function still needs to know how to index by size bin, the caller only needs the filename label. Don't dedupe; keep both.

Also add the import for `get_source` at the top of `species_optics.py` — find the imports block (lines 1-14) and add this line:

```python
from sources import get_source
```

- [ ] **Step 6: Quick smoke test — argparse and dispatch**

Run:
```bash
python -c "
import sys
sys.argv = ['species_optics.py', '--source', 'merra2', '--help']
try:
    import species_optics
except SystemExit:
    pass
" 2>&1 | grep -A1 source
```

Expected: `--source` flag appears in the help with `{geosit,merra2}` choices.

Then run:
```bash
python -c "
import sys
sys.argv = ['species_optics.py', '--source', 'invalid_src']
try:
    import species_optics
except SystemExit as e:
    print('argparse rejected, exit code', e.code)
"
```

Expected: argparse error message naming the valid choices, exit code 2.

- [ ] **Step 7: Commit**

```bash
git add species_optics.py
git commit -m "species_optics: --source flag and Source-driven dispatch"
```

---

### Task 6: GEOS-IT regression check for `species_optics.py`

Re-run a known GEOS-IT day with the refactored code and confirm byte-identical subsampled output against the baseline at `/CERES/sarb/dfillmor/GEOSIT_alpha_4/2008/07/`.

**Files:** None (verification only).

- [ ] **Step 1: Run one timestep, one species, one band against a temp outdir**

Pick: 2008-07-01T00, species SU (→ SO4), band sw01. Use a temp outdir so we don't overwrite the baseline.

```bash
TMPOUT=$(mktemp -d -t merra2_regression.XXXXXX)
echo "Temp outdir: $TMPOUT"

python species_optics.py \
    --source geosit \
    --species SU \
    --band sw01 \
    --start 2008-07-01T00 \
    --end 2008-07-01T00 \
    --ceres \
    --workdir "$TMPOUT"
```

Expected: writes `${TMPOUT}/GEOSIT_alpha_4/2008/07/GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.SO4_SW01.2008-07-01T0000.V01.nc4` and prints `AOD Global Mean ...`.

- [ ] **Step 2: Byte-compare against baseline**

Run:
```bash
diff -q \
    "${TMPOUT}/GEOSIT_alpha_4/2008/07/GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.SO4_SW01.2008-07-01T0000.V01.nc4" \
    "/CERES/sarb/dfillmor/GEOSIT_alpha_4/2008/07/GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.SO4_SW01.2008-07-01T0000.V01.nc4"
```

Expected: no output (files identical).

**If the diff fails:** there's a subtle difference — most likely the `input_filename` or `processing_datetime` attrs (the latter is wall-clock and will always differ). Compare with `ncdump`:

```bash
ncdump -h "${TMPOUT}/GEOSIT_alpha_4/2008/07/GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.SO4_SW01.2008-07-01T0000.V01.nc4" > /tmp/new.cdl
ncdump -h "/CERES/sarb/dfillmor/GEOSIT_alpha_4/2008/07/GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.SO4_SW01.2008-07-01T0000.V01.nc4" > /tmp/old.cdl
diff /tmp/new.cdl /tmp/old.cdl
```

Expected differences: only `:processing_datetime = "..."` and possibly `:datetime = "..."` (the latter being the bug-fix where today's GEOS-IT produces `asm` instead of a real date). If anything else differs, investigate before continuing.

For comparing the actual array values, use:

```bash
python -c "
import xarray as xr
a = xr.open_dataset('${TMPOUT}/GEOSIT_alpha_4/2008/07/GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.SO4_SW01.2008-07-01T0000.V01.nc4')
b = xr.open_dataset('/CERES/sarb/dfillmor/GEOSIT_alpha_4/2008/07/GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.SO4_SW01.2008-07-01T0000.V01.nc4')
for v in a.data_vars:
    import numpy as np
    eq = np.array_equal(a[v].values, b[v].values)
    print(f'{v}: identical={eq}')
"
```

Expected: every variable `identical=True`.

- [ ] **Step 3: Cleanup**

```bash
rm -rf "$TMPOUT"
```

- [ ] **Step 4: No commit (verification task)**

If Step 2 passes (or only differs on processing_datetime + datetime attrs), the refactor is sound. No code change in this task.

---

### Task 7: Wire `external_mix.py` to the source dispatch

Simpler than Task 5 — no process_file refactor, just argparse + default-pattern selection.

**Files:**
- Modify: `external_mix.py` — argparse (~line 143-145, 152-156), `--ceres` block (~lines 169-171), main loop (~line 182-191).

- [ ] **Step 1: Add `--source` argparse flag and change `--file_pattern` default to None**

In `external_mix.py`, find this block (lines 143-145):

```python
    parser.add_argument('--file_pattern', type=str,
        default=os.path.join('GEOSIT', 'YYYY', 'MM',
            'GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.*_band.YYYY-MM-DDTHH00.V01.nc4'))
```

Replace with:

```python
    parser.add_argument('--file_pattern', type=str, default=None,
        help='glob pattern for per-species inputs under --datadir; '
             'defaults to the --source default (see sources.py)')
    parser.add_argument('--source', choices=['geosit', 'merra2'],
        default='geosit',
        help='input data source whose per-species outputs we mix')
```

- [ ] **Step 2: Drop the `--ceres` file_pattern remap**

Find this block (lines 169-171):

```python
    if args.ceres:
        args.datadir = '/CERES/sarb/dfillmor/'
        args.file_pattern = args.file_pattern.replace('GEOSIT/', 'GEOSIT_alpha_4/')
```

Replace with:

```python
    if args.ceres:
        args.datadir = '/CERES/sarb/dfillmor/'
```

- [ ] **Step 3: Wire source dispatch before the main loop**

Find this block (lines 182-183):

```python
    dates = pd.date_range(start=args.start, end=args.end, freq='3h')
    logging.info(dates)
```

Replace with:

```python
    src = get_source(args.source)
    if args.file_pattern is None:
        args.file_pattern = src.species_glob_pattern
    dates = pd.date_range(start=args.start, end=args.end, freq=src.cadence)
    logging.info(dates)
```

Add the import at the top of the file (with the other imports, lines 1-12):

```python
from sources import get_source
```

- [ ] **Step 4: Smoke-test argparse**

Run:
```bash
python -c "
import sys
sys.argv = ['external_mix.py', '--help']
try:
    import external_mix
except SystemExit:
    pass
" 2>&1 | grep -A1 source
```

Expected: `--source` choices `{geosit,merra2}` visible.

- [ ] **Step 5: Commit**

```bash
git add external_mix.py
git commit -m "external_mix: --source flag and Source-driven dispatch"
```

---

### Task 8: GEOS-IT regression check for `external_mix.py`

**Files:** None.

- [ ] **Step 1: Run external_mix for one band, one timestep, against the existing GEOS-IT outputs**

First, copy the existing per-species GEOS-IT outputs for 2008-07-01T00 SW01 to a temp dir (since external_mix writes the AER file next to the inputs):

```bash
TMPOUT=$(mktemp -d -t external_mix_regression.XXXXXX)
mkdir -p "${TMPOUT}/GEOSIT_alpha_4/2008/07"

# Copy all per-species inputs for 2008-07-01T00 SW01
cp /CERES/sarb/dfillmor/GEOSIT_alpha_4/2008/07/GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.*_SW01.2008-07-01T0000.V01.nc4 "${TMPOUT}/GEOSIT_alpha_4/2008/07/"

# Drop any preexisting AER file from the copy (we want external_mix to produce it fresh)
rm -f "${TMPOUT}/GEOSIT_alpha_4/2008/07/"*AER_SW01*

ls "${TMPOUT}/GEOSIT_alpha_4/2008/07/" | wc -l
```

Expected: 18 input files (one per species/bin: SO4, OCPHOBIC, OCPHILIC, BCPHOBIC, BCPHILIC, SS001-005, DU001-005, NO3AN1-3 = 5+5+5+3=18).

Run external_mix against the temp tree:

```bash
python external_mix.py \
    --source geosit \
    --band sw01 \
    --start 2008-07-01T00 \
    --end 2008-07-01T00 \
    --ceres \
    --workdir "$TMPOUT"
```

Expected: writes `${TMPOUT}/GEOSIT_alpha_4/2008/07/GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.AER_SW01.2008-07-01T0000.V01.nc4`.

- [ ] **Step 2: Compare arrays against baseline**

```bash
python -c "
import xarray as xr
import numpy as np
a = xr.open_dataset('${TMPOUT}/GEOSIT_alpha_4/2008/07/GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.AER_SW01.2008-07-01T0000.V01.nc4')
b = xr.open_dataset('/CERES/sarb/dfillmor/GEOSIT_alpha_4/2008/07/GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.AER_SW01.2008-07-01T0000.V01.nc4')
for v in ['Extinction_Layer_Optical_Depth', 'Scattering_Layer_Optical_Depth', 'Layer_Asymmetry_Parameter', 'Extinction_Column_Optical_Depth']:
    eq = np.allclose(a[v].values, b[v].values, equal_nan=True)
    print(f'{v}: allclose={eq}')
"
```

Expected: every variable `allclose=True`.

- [ ] **Step 3: Cleanup**

```bash
rm -rf "$TMPOUT"
```

- [ ] **Step 4: No commit (verification task).**

---

### Task 9: Pass `--source` through `run_species_optics.sh` and `run_external_mix.sh`

**Files:**
- Modify: `run_species_optics.sh` — add `--source` parsing to the wrapper's argparse loop.
- Modify: `run_external_mix.sh` — same.

- [ ] **Step 1: Update `run_species_optics.sh`**

Find the usage and argparse block at the top of `run_species_optics.sh` (lines 8-47):

```bash
usage() {
    echo "Usage: $0 [--bands sw01,sw02,...|all] [--optics_tmpdir DIR|auto] [extra species_optics.py args]" >&2
    echo "Example: $0 --bands sw01,lw01 --optics_tmpdir auto --start 2010-01-01T00 --end 2010-01-01T00" >&2
    echo "" >&2
    echo "  --optics_tmpdir DIR   Use DIR for local optics file copies (avoids file locking)" >&2
    echo "  --optics_tmpdir auto  Auto-create a temp directory (cleaned up on exit)" >&2
    exit 1
}

BANDS=()
OPTICS_TMPDIR=""
AUTO_TMPDIR=0
WVL=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bands)
            IFS=',' read -ra BANDS <<< "$2"
            shift 2
            ;;
        --wvl)
            WVL="$2"
            shift 2
            ;;
```

Add `--source` documentation and parsing. Replace `usage()` first line and the initialization block:

```bash
usage() {
    echo "Usage: $0 [--bands sw01,sw02,...|all] [--source geosit|merra2] [--optics_tmpdir DIR|auto] [extra species_optics.py args]" >&2
    echo "Example: $0 --bands sw01,lw01 --optics_tmpdir auto --start 2010-01-01T00 --end 2010-01-01T00" >&2
    echo "" >&2
    echo "  --source SOURCE       Input data source (geosit | merra2; default geosit)" >&2
    echo "  --optics_tmpdir DIR   Use DIR for local optics file copies (avoids file locking)" >&2
    echo "  --optics_tmpdir auto  Auto-create a temp directory (cleaned up on exit)" >&2
    exit 1
}

BANDS=()
SOURCE="geosit"
OPTICS_TMPDIR=""
AUTO_TMPDIR=0
WVL=""
```

Add the `--source` case alongside `--bands`/`--wvl`:

```bash
        --source)
            SOURCE="$2"
            shift 2
            ;;
```

(Insert after the `--wvl)` case block, before `--optics_tmpdir)`.)

Find the `python species_optics.py` call (around line 106):

```bash
        python species_optics.py --species "$SP" "${BAND_ARGS[@]}" "${TMPDIR_ARG[@]+"${TMPDIR_ARG[@]}"}" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
```

Replace with (add `--source "$SOURCE"`):

```bash
        python species_optics.py --source "$SOURCE" --species "$SP" "${BAND_ARGS[@]}" "${TMPDIR_ARG[@]+"${TMPDIR_ARG[@]}"}" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
```

There are three nearly-identical `python species_optics.py` lines (for SPECIES_NO_BIN, SPECIES_5BIN, SPECIES_3BIN — lines 106, 112, 119). Update all three.

Also update the corresponding `echo ">>> species_optics.py …"` lines (105, 111, 118) for log clarity:

```bash
        echo ">>> species_optics.py --source $SOURCE --species $SP ${BAND_ARGS[*]} ${TMPDIR_ARG[*]:-} ${EXTRA_ARGS[*]:-}"
```

- [ ] **Step 2: Syntax check `run_species_optics.sh`**

```bash
bash -n run_species_optics.sh && echo "syntax OK"
```

Expected: `syntax OK`.

- [ ] **Step 3: Smoke-test `--help`**

```bash
./run_species_optics.sh --help 2>&1 | head -10
```

Expected: usage text includes `--source geosit|merra2`.

- [ ] **Step 4: Update `run_external_mix.sh` — argparse + python call**

In `run_external_mix.sh`, find the usage block (lines 8-12):

```bash
usage() {
    echo "Usage: $0 [--bands sw01,sw02,...|all] [--no-clean] [--clean-species] [--day-date YYYY-MM-DD] [extra external_mix.py args]" >&2
    echo "Example: $0 --bands sw01,lw01 --start 2010-01-01T00 --end 2010-01-01T00" >&2
    exit 1
}
```

Replace with:

```bash
usage() {
    echo "Usage: $0 [--bands sw01,sw02,...|all] [--source geosit|merra2] [--no-clean] [--clean-species] [--day-date YYYY-MM-DD] [extra external_mix.py args]" >&2
    echo "Example: $0 --bands sw01,lw01 --start 2010-01-01T00 --end 2010-01-01T00" >&2
    echo "" >&2
    echo "  --source SOURCE  Input data source (geosit | merra2; default geosit)" >&2
    exit 1
}
```

Find the variable initialization (lines 14-18):

```bash
BANDS=()
CLEAN_AER=1
CLEAN_SPECIES=0
WVL=""
DAY_DATE=""
```

Replace with:

```bash
BANDS=()
SOURCE="geosit"
CLEAN_AER=1
CLEAN_SPECIES=0
WVL=""
DAY_DATE=""
```

Find the argparse `case` block (lines 20-49). Insert this case after the `--wvl)` case and before `--no-clean)`:

```bash
        --source)
            SOURCE="$2"
            shift 2
            ;;
```

Find the python invocation (line 128):

```bash
    python external_mix.py "${PY_BAND_ARGS[@]}" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
```

Replace with:

```bash
    python external_mix.py --source "$SOURCE" "${PY_BAND_ARGS[@]}" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
```

Also update the echo above it (line 127):

```bash
    echo ">>> external_mix.py --source $SOURCE ${PY_BAND_ARGS[*]} ${EXTRA_ARGS[*]:-}"
```

- [ ] **Step 5: Make `run_external_mix.sh` cleanup SUBDIR source-aware**

The wrapper has its own cleanup logic that walks `${DATADIR}/${SUBDIR}` looking for AER and per-species files to delete. SUBDIR is currently hardcoded to `GEOSIT` or `GEOSIT_alpha_4`.

Find this block (lines 55-76):

```bash
# Detect data root for cleanup based on args (very lightweight parsing)
DATADIR="${HOME}/Data"
SUBDIR="GEOSIT"
for ((i=0; i<${#EXTRA_ARGS[@]}; i++)); do
    case "${EXTRA_ARGS[i]}" in
        --ceres)
            DATADIR="/CERES/sarb/dfillmor"
            SUBDIR="GEOSIT_alpha_4"
            ;;
        --datadir)
            # Next arg should be the path
            if (( i + 1 < ${#EXTRA_ARGS[@]} )); then
                DATADIR="${EXTRA_ARGS[i+1]}"
            fi
            ;;
        --workdir)
            if (( i + 1 < ${#EXTRA_ARGS[@]} )); then
                DATADIR="${EXTRA_ARGS[i+1]}"
            fi
            ;;
    esac
done
```

Replace with:

```bash
# Detect data root for cleanup based on args (very lightweight parsing)
DATADIR="${HOME}/Data"
case "$SOURCE" in
    merra2)
        SUBDIR_DEFAULT="MERRA2"
        SUBDIR_CERES="MERRA2_alpha_4"
        ;;
    geosit)
        SUBDIR_DEFAULT="GEOSIT"
        SUBDIR_CERES="GEOSIT_alpha_4"
        ;;
    *)
        echo "Error: unknown --source value '$SOURCE' (expected geosit|merra2)" >&2
        exit 1
        ;;
esac
SUBDIR="$SUBDIR_DEFAULT"
for ((i=0; i<${#EXTRA_ARGS[@]}; i++)); do
    case "${EXTRA_ARGS[i]}" in
        --ceres)
            DATADIR="/CERES/sarb/dfillmor"
            SUBDIR="$SUBDIR_CERES"
            ;;
        --datadir)
            # Next arg should be the path
            if (( i + 1 < ${#EXTRA_ARGS[@]} )); then
                DATADIR="${EXTRA_ARGS[i+1]}"
            fi
            ;;
        --workdir)
            if (( i + 1 < ${#EXTRA_ARGS[@]} )); then
                DATADIR="${EXTRA_ARGS[i+1]}"
            fi
            ;;
    esac
done
```

- [ ] **Step 6: Verify syntax and help for `run_external_mix.sh`**

```bash
bash -n run_external_mix.sh && echo "syntax OK"
./run_external_mix.sh --help 2>&1 | head -10
```

Expected: `syntax OK`, then usage text shows the `--source` line.

- [ ] **Step 7: Commit**

```bash
git add run_species_optics.sh run_external_mix.sh
git commit -m "shell wrappers: pass --source through to species_optics + external_mix"
```

---

### Task 10: Pass `--source` through `run_daily_processing.sh` with source-aware skip-check

This wrapper has three touch-points (per the spec): argparse, `SKIP_SUBDIR` resolution, and `is_day_complete` glob suffix.

**Files:**
- Modify: `run_daily_processing.sh` — usage text, argparse, SKIP_SUBDIR resolution (lines 158-178), is_day_complete (lines 183-191).

- [ ] **Step 1: Add `--source` flag to argparse**

Find the usage block (around line 18-41):

```bash
    echo "  --ceres         Pass --ceres flag to processing scripts" >&2
```

Insert a `--source` line right above it:

```bash
    echo "  --source SOURCE Input data source: geosit | merra2 (default geosit)" >&2
    echo "  --ceres         Pass --ceres flag to processing scripts" >&2
```

Find the variable initialization block (lines 43-50):

```bash
START_DATE=""
END_DATE=""
LOGDIR="./logs"
MAX_JOBS=0
DRY_RUN=0
DETACH=0
SKIP_COMPLETE=0
EXTRA_ARGS=()
```

Add `SOURCE="geosit"`:

```bash
START_DATE=""
END_DATE=""
LOGDIR="./logs"
MAX_JOBS=0
DRY_RUN=0
DETACH=0
SKIP_COMPLETE=0
SOURCE="geosit"
EXTRA_ARGS=()
```

Add the `--source` case to the argparse loop. Find the `--ceres` case (lines 82-85):

```bash
        --ceres)
            EXTRA_ARGS+=(--ceres)
            shift
            ;;
```

Insert before it:

```bash
        --source)
            SOURCE="$2"
            EXTRA_ARGS+=(--source "$2")
            shift 2
            ;;
```

- [ ] **Step 2: Make `SKIP_SUBDIR` source-aware**

Find the block (lines 158-178):

```bash
# Resolve output root for completeness checks (mirrors run_external_mix.sh)
SKIP_DATADIR="${HOME}/Data"
SKIP_SUBDIR="GEOSIT"
for ((i=0; i<${#EXTRA_ARGS[@]}; i++)); do
    case "${EXTRA_ARGS[i]}" in
        --ceres)
            SKIP_DATADIR="/CERES/sarb/dfillmor"
            SKIP_SUBDIR="GEOSIT_alpha_4"
            ;;
        --datadir)
            if (( i + 1 < ${#EXTRA_ARGS[@]} )); then
                SKIP_DATADIR="${EXTRA_ARGS[i+1]}"
            fi
            ;;
        --workdir)
            if (( i + 1 < ${#EXTRA_ARGS[@]} )); then
                SKIP_DATADIR="${EXTRA_ARGS[i+1]}"
            fi
            ;;
    esac
done
```

Replace with:

```bash
# Resolve output root for completeness checks (mirrors run_external_mix.sh)
SKIP_DATADIR="${HOME}/Data"
case "$SOURCE" in
    merra2)
        SKIP_SUBDIR_DEFAULT="MERRA2"
        SKIP_SUBDIR_CERES="MERRA2_alpha_4"
        ;;
    geosit)
        SKIP_SUBDIR_DEFAULT="GEOSIT"
        SKIP_SUBDIR_CERES="GEOSIT_alpha_4"
        ;;
    *)
        echo "Error: unknown --source value '$SOURCE' (expected geosit|merra2)" >&2
        exit 1
        ;;
esac
SKIP_SUBDIR="$SKIP_SUBDIR_DEFAULT"
for ((i=0; i<${#EXTRA_ARGS[@]}; i++)); do
    case "${EXTRA_ARGS[i]}" in
        --ceres)
            SKIP_DATADIR="/CERES/sarb/dfillmor"
            SKIP_SUBDIR="$SKIP_SUBDIR_CERES"
            ;;
        --datadir)
            if (( i + 1 < ${#EXTRA_ARGS[@]} )); then
                SKIP_DATADIR="${EXTRA_ARGS[i+1]}"
            fi
            ;;
        --workdir)
            if (( i + 1 < ${#EXTRA_ARGS[@]} )); then
                SKIP_DATADIR="${EXTRA_ARGS[i+1]}"
            fi
            ;;
    esac
done
```

- [ ] **Step 3: Make `is_day_complete` source-aware**

Find the block (lines 183-191):

```bash
is_day_complete() {
    local day_date="$1"
    local outdir="${SKIP_DATADIR}/${SKIP_SUBDIR}/${day_date:0:4}/${day_date:5:2}"
    [[ -d "$outdir" ]] || return 1
    local n_sw n_lw
    n_sw=$(find "$outdir" -maxdepth 1 -type f -name "*AER_SW*.${day_date}T*.V01.nc4" 2>/dev/null | wc -l)
    n_lw=$(find "$outdir" -maxdepth 1 -type f -name "*AER_LW*.${day_date}T*.V01.nc4" 2>/dev/null | wc -l)
    (( n_sw + n_lw >= EXPECTED_AER_PER_DAY ))
}
```

Replace with:

```bash
case "$SOURCE" in
    merra2) AER_NAME_SUFFIX=".nc4" ;;
    geosit) AER_NAME_SUFFIX=".V01.nc4" ;;
esac

is_day_complete() {
    local day_date="$1"
    local outdir="${SKIP_DATADIR}/${SKIP_SUBDIR}/${day_date:0:4}/${day_date:5:2}"
    [[ -d "$outdir" ]] || return 1
    local n_sw n_lw
    n_sw=$(find "$outdir" -maxdepth 1 -type f -name "*AER_SW*.${day_date}T*${AER_NAME_SUFFIX}" 2>/dev/null | wc -l)
    n_lw=$(find "$outdir" -maxdepth 1 -type f -name "*AER_LW*.${day_date}T*${AER_NAME_SUFFIX}" 2>/dev/null | wc -l)
    (( n_sw + n_lw >= EXPECTED_AER_PER_DAY ))
}
```

- [ ] **Step 4: Syntax + dry-run check**

```bash
bash -n run_daily_processing.sh && echo "syntax OK"

./run_daily_processing.sh --source merra2 --start 2008-07-01 --end 2008-07-01 --ceres --dry-run
```

Expected: `syntax OK`, then dry-run says `[DRY RUN] Would launch job for 2008-07-01` (and reports launch counts).

- [ ] **Step 5: Commit**

```bash
git add run_daily_processing.sh
git commit -m "run_daily_processing: --source flag with source-aware skip-check"
```

---

### Task 11: Add `--source` to `check_aer_grid.py`

QC script needs the same source toggle so it can read either tree.

**Files:**
- Modify: `check_aer_grid.py` — argparse (~line 334), subdir + filename template lookup (lines 50-56), source_glob substitution (line 407).

- [ ] **Step 1: Add `--source` argparse flag**

In `check_aer_grid.py`, find this block (lines 333-334):

```python
    parser.add_argument('--ceres', action='store_true',
                        help='use CERES production paths (GEOSIT_alpha_4)')
```

Replace with:

```python
    parser.add_argument('--ceres', action='store_true',
                        help='use CERES production paths')
    parser.add_argument('--source', choices=['geosit', 'merra2'],
                        default='geosit',
                        help='input data source whose AER outputs to QC')
```

Add the import at the top of the file. Find the import block (lines 9-16):

```python
import argparse
import datetime
import logging
import os
import sys

import numpy as np
import xarray as xr
```

Add a `from sources import get_source` import (after the `xr` import, at the bottom of the imports):

```python
import argparse
import datetime
import logging
import os
import sys

import numpy as np
import xarray as xr

from sources import get_source
```

- [ ] **Step 2: Make `build_paths` source-aware**

Find the entire `build_paths` function (lines 41-62):

```python
def build_paths(datadir, ceres, date, band, workdir=None):
    """Return the 8 expected timestep file paths for one (band, date).

    date: 'YYYY-MM-DD'
    band: uppercase, e.g. 'SW01'
    """
    yyyy, mm, _ = date.split('-')
    if ceres:
        base = workdir if workdir else '/CERES/sarb/dfillmor'
        subdir = 'GEOSIT_alpha_4'
    else:
        base = datadir
        subdir = 'GEOSIT'
    fname_tmpl = (
        'GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.'
        'AER_{band}.{date}{ts}.V01.nc4'
    )
    return [
        os.path.join(base, subdir, yyyy, mm,
                     fname_tmpl.format(band=band, date=date, ts=ts))
        for ts in TIMESTEPS
    ]
```

Replace with:

```python
def build_paths(datadir, ceres, date, band, workdir=None, source='geosit'):
    """Return the 8 expected timestep file paths for one (band, date).

    date: 'YYYY-MM-DD'
    band: uppercase, e.g. 'SW01'
    source: 'geosit' or 'merra2' — picks subdir and filename template.
    """
    yyyy, mm, _ = date.split('-')
    src = get_source(source)
    if ceres:
        base = workdir if workdir else '/CERES/sarb/dfillmor'
        subdir = src.output_subdir
    else:
        base = datadir
        # Non-CERES uses the bare-source layout: 'GEOSIT' / 'MERRA2'
        # (matches the input-tree convention, not the _alpha_4 output tree).
        subdir = src.output_subdir.replace('_alpha_4', '')
    return [
        os.path.join(base, subdir, yyyy, mm,
                     src.aer_filename_template.format(
                         band=band, date=date, ts=ts))
        for ts in TIMESTEPS
    ]
```

- [ ] **Step 3: Update `load_window_mean` and call sites to pass `source` through**

`build_paths` is called from two places. Run:

```bash
grep -n "build_paths(" check_aer_grid.py
```

Expected: two matches — one inside `load_window_mean` (around line 106), one in `main()` (around line 405).

Find the `load_window_mean` signature and its internal `build_paths` call. The current signature (around line 65) is:

```python
def load_window_mean(datadir, ceres, dates, band, workdir=None):
```

Replace with:

```python
def load_window_mean(datadir, ceres, dates, band, workdir=None, source='geosit'):
```

Then find its `build_paths` call inside (around line 106):

```python
        paths = build_paths(datadir, ceres, date, band, workdir=workdir)
```

Replace with:

```python
        paths = build_paths(datadir, ceres, date, band,
                            workdir=workdir, source=source)
```

Now update the two call sites in `main()`. Find this block (lines 395-407):

```python
        field, lat, lon, n_found, n_total, n_days_data, n_days_total = (
            load_window_mean(args.datadir, args.ceres, dates, band,
                             workdir=args.workdir))
        if n_found == 0:
            logging.error('Skipping band %s: no usable data in window', band)
            any_failed = True
            continue
        stats = aggregate_cells(field, lat)
        # Use a glob-style source string so the report shows the pattern
        # rather than every individual path.
        first_paths = build_paths(args.datadir, args.ceres, dates[0], band,
                                  workdir=args.workdir)
        source_glob = first_paths[0].replace('T0000.V01.nc4', 'T*.V01.nc4')
```

Replace with:

```python
        field, lat, lon, n_found, n_total, n_days_data, n_days_total = (
            load_window_mean(args.datadir, args.ceres, dates, band,
                             workdir=args.workdir, source=args.source))
        if n_found == 0:
            logging.error('Skipping band %s: no usable data in window', band)
            any_failed = True
            continue
        stats = aggregate_cells(field, lat)
        # Use a glob-style source string so the report shows the pattern
        # rather than every individual path.
        first_paths = build_paths(args.datadir, args.ceres, dates[0], band,
                                  workdir=args.workdir, source=args.source)
        if args.source == 'merra2':
            source_glob = first_paths[0].replace('T0000.nc4', 'T*.nc4')
        else:
            source_glob = first_paths[0].replace(
                'T0000.V01.nc4', 'T*.V01.nc4')
```

- [ ] **Step 4: Smoke-test argparse and a GEOS-IT regression run**

Help check:

```bash
./check_aer_grid.py --help 2>&1 | grep -A1 source
```

Expected: `--source` choices `{geosit,merra2}` visible.

GEOS-IT regression — produce the QC report into a temp dir and compare against the in-repo baseline:

```bash
./check_aer_grid.py --date 2008-07-01 --bands sw01 --ceres --outdir /tmp/qc_test
diff /tmp/qc_test/aer_check_SW01_2008-07-01.txt qc/aer_check_SW01_2008-07-01.txt
```

Expected: empty diff (byte-identical text report).

If the baseline `qc/aer_check_SW01_2008-07-01.txt` is not present in the repo, just confirm the report looks sane:

```bash
cat /tmp/qc_test/aer_check_SW01_2008-07-01.txt
```

Expected: header with `source_glob = /CERES/sarb/dfillmor/GEOSIT_alpha_4/...T*.V01.nc4`, a global-mean line with a plausible AOD value, and a 9×18 map.

Cleanup:

```bash
rm -rf /tmp/qc_test
```

- [ ] **Step 5: Commit**

```bash
git add check_aer_grid.py
git commit -m "check_aer_grid: --source flag for QC against either source tree"
```

---

### Task 12: Update README.md with MERRA-2 invocation examples

**Files:**
- Modify: `README.md` — add a `--source` note under "Batch Processing" and a MERRA-2 example.

- [ ] **Step 1: Read the current "Batch Processing" section**

```bash
sed -n '18,70p' README.md
```

Get a feel for the existing structure.

- [ ] **Step 2: Add a MERRA-2 example after the existing Single Band Processing block**

Find the section that ends with `--ceres --workdir /CERES/sarb/myuser/ --optics-dir /CERES/sarb/myuser/Optics` (around line 43-44) and the closing ` ``` `. Insert a new subsection after that block, before the "### Daily Processing Pipeline" header:

```markdown
### MERRA-2 input

To process MERRA-2 `inst3_3d_aer_Nv` daily files instead of GEOS-IT,
pass `--source merra2`. MERRA-2 files are daily (8 timesteps per
file), so the start/end pair should be a single hour (e.g.
`--start 2008-07-01T00 --end 2008-07-01T00`); the script reads all
8 timesteps from the matched daily file and writes 8 per-timestep
outputs.

```bash
./run_species_optics.sh --source merra2 --bands sw01,sw02 \
    --start 2008-07-01T00 --end 2008-07-01T00 --ceres
./run_external_mix.sh --source merra2 --bands sw01,sw02 \
    --start 2008-07-01T00 --end 2008-07-01T00 --ceres
```

Outputs land under `${workdir}/MERRA2_alpha_4/YYYY/MM/` with names
like `MERRA2.aer_inst_3hr_glo_L288x180_v24.AER_SW01.2008-07-01T0000.nc4`.

The MERRA-2 stream prefix (`MERRA2_100`/`200`/`300`/`400`) is auto-
selected by year via a glob in `sources.py`; no manual mapping is
needed.

```

- [ ] **Step 3: Update the Daily Processing Pipeline options list**

Find the existing `--ceres` line in the options list (around line 60):

```markdown
- `--ceres` - Use CERES production data paths
```

Insert a `--source` line above it:

```markdown
- `--source SOURCE` - Input data source: `geosit` (default, 3-hourly files) or `merra2` (daily files)
- `--ceres` - Use CERES production data paths
```

- [ ] **Step 4: Spot-check the rendered Markdown**

```bash
sed -n '18,110p' README.md
```

Expected: the new "MERRA-2 input" subsection is between "Single Band Processing" and "Daily Processing Pipeline"; the new `--source` option is in the options list.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "README: document --source flag and MERRA-2 invocation"
```

---

### Task 13: MERRA-2 smoke test — end-to-end on 2008-07-01

The final verification. Run the full pipeline for one day and two bands against MERRA-2 input and confirm the output is plausible.

**Files:** None (verification only).

- [ ] **Step 1: Confirm input data is present**

```bash
ls -la /CERES_prd/GMAO/MERRA2/2008/07/MERRA2_300.inst3_3d_aer_Nv.20080701.nc4
```

Expected: file exists with nonzero size.

Quickly inspect variables:

```bash
ncdump -h /CERES_prd/GMAO/MERRA2/2008/07/MERRA2_300.inst3_3d_aer_Nv.20080701.nc4 | grep -E '^\s*(float|double)' | head -20
```

Expected: variables include `RH`, `DELP`, `PS`, `SO4`, `BCPHOBIC`, `BCPHILIC`, `OCPHOBIC`, `OCPHILIC`, `DU001..DU005`, `SS001..SS005`, `NO3AN1..NO3AN3`.

- [ ] **Step 2: Run `species_optics` for sw01 and lw01**

```bash
TMPOUT=$(mktemp -d -t merra2_smoke.XXXXXX)
echo "Smoke test outdir: $TMPOUT"

./run_species_optics.sh \
    --source merra2 \
    --bands sw01,lw01 \
    --optics_tmpdir auto \
    --start 2008-07-01T00 \
    --end 2008-07-01T00 \
    --ceres \
    --workdir "$TMPOUT" 2>&1 | tail -30
```

Expected: script runs through all species (SO4, OCPHOBIC, OCPHILIC, BCPHOBIC, BCPHILIC, SS001-005, DU001-005, NO3AN1-3) for both bands, prints `AOD Global Mean ...` lines, exits 0.

Verify the output tree:

```bash
ls "${TMPOUT}/MERRA2_alpha_4/2008/07/" | head -20
ls "${TMPOUT}/MERRA2_alpha_4/2008/07/" | wc -l
```

Expected: filenames like `MERRA2.aer_inst_3hr_glo_L288x180_v24.SO4_SW01.2008-07-01T0000.nc4` etc. Count = 18 species × 2 bands × 8 timesteps = **288 files**.

- [ ] **Step 3: Run `external_mix` for sw01 and lw01**

```bash
./run_external_mix.sh \
    --source merra2 \
    --bands sw01,lw01 \
    --start 2008-07-01T00 \
    --end 2008-07-01T00 \
    --ceres \
    --workdir "$TMPOUT" 2>&1 | tail -20
```

Expected: writes `MERRA2.aer_inst_3hr_glo_L288x180_v24.AER_SW01.2008-07-01T<HH>00.nc4` and the LW01 counterpart for each of 8 timesteps. Prints `Total AOD Global Mean ...` for each.

Verify:

```bash
find "${TMPOUT}/MERRA2_alpha_4/2008/07/" -name '*AER_SW01*' | wc -l
find "${TMPOUT}/MERRA2_alpha_4/2008/07/" -name '*AER_LW01*' | wc -l
```

Expected: 8 each.

- [ ] **Step 4: QC with `check_aer_grid.py`**

```bash
./check_aer_grid.py \
    --source merra2 \
    --date 2008-07-01 \
    --bands sw01,lw01 \
    --ceres \
    --workdir "$TMPOUT" \
    --outdir "${TMPOUT}/qc"

cat "${TMPOUT}/qc/aer_check_SW01_2008-07-01.txt"
```

Expected:
- Global mean AOD reported in the ~0.05 to ~0.5 range (not zero, not NaN).
- The 9×18 regional-mean map shows elevated values over Sahara (~20-30N, 0-30E) and East Asia (~20-40N, 100-130E).
- No "No timestep files found" errors.

If the global mean looks suspicious (e.g., zero, NaN, or wildly off), investigate before declaring success.

- [ ] **Step 5: Cleanup**

```bash
rm -rf "$TMPOUT"
```

- [ ] **Step 6: No commit (verification task).**

Once the smoke test passes, the feature is complete.

---

## Self-Review Checklist

After implementing all tasks, verify against the spec:

1. **`--source` flag exists on:** species_optics.py ✓ (Task 5), external_mix.py ✓ (Task 7), run_species_optics.sh ✓ (Task 9), run_external_mix.sh ✓ (Task 9), run_daily_processing.sh ✓ (Task 10), check_aer_grid.py ✓ (Task 11).
2. **`sources.py`** has both `SOURCES['geosit']` and `SOURCES['merra2']` entries with all 7 fields + 2 callables. ✓ (Tasks 2-4).
3. **GEOS-IT byte-identical** behavior preserved. ✓ Verified in Tasks 6 and 8.
4. **MERRA-2 produces 8 per-timestep outputs per day, both for SW and LW bands.** ✓ Verified in Task 13.
5. **`kill_daily_jobs.sh`** unchanged — no source-specific strings. ✓ (Confirmed in spec).
6. **README** documents the new flag and gives a MERRA-2 example. ✓ (Task 12).
7. **No placeholders, TODOs, or "TBD"s** in any of the tasks. ✓ (Each task shows exact code).
