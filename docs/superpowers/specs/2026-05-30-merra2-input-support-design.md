# MERRA-2 input support for species_optics + external_mix — design

Date: 2026-05-30

## Purpose

Add permanent support for MERRA-2 `inst3_3d_aer_Nv` input alongside the
existing GEOS-IT input path. Today's behavior:

- `species_optics.py` and `external_mix.py` accept only GEOS-IT input
  in practice — `--ceres` unconditionally rewrites `args.file_pattern`
  to the GEOS-IT template, and the output-filename logic uses
  `.replace('GEOS5294.', ...)` / `.replace('L576x361_v72', ...)` which
  are no-ops on MERRA-2 paths.
- The MERRA-2 optics referenced from `aerosol_ceres.yaml` are still
  fully wired up — only the input data path is biased to GEOS-IT.

After this change:

- A new `--source {geosit,merra2}` flag selects the input data
  source. Default is `geosit`; existing GEOS-IT runs are byte-identical.
- MERRA-2 produces eight per-timestep output files per daily input,
  matching the GEOS-IT output cadence so downstream consumers (Fu-Liou)
  see the same per-3h file shape regardless of source.
- The shell wrappers, the daily-batch driver, and the AER QC script
  all gain a passthrough `--source` flag.

## Scope

In scope:

- `sources.py` (new) — registry of source-specific knowledge.
- `species_optics.py` — argparse, file pattern handling, dataset open
  + timestep loop reshape, output filename construction.
- `external_mix.py` — argparse, source-aware default glob pattern.
- `run_species_optics.sh`, `run_external_mix.sh` — pass `--source`
  through to Python.
- `run_daily_processing.sh` — pass `--source` through, plus
  source-aware `SKIP_SUBDIR` and `is_day_complete` glob.
- `check_aer_grid.py` — source-aware subdir and AER filename template.
- `tests/test_sources.py` (new) — unit tests pinning both registry
  entries and the GEOS-IT equivalence guarantee.

Out of scope:

- A `--source geosfp` or any third source. The dispatch table makes
  this trivial to add later; not needed now.
- Multi-source averaging or cross-source comparison plots
  (`plot_diff.py` etc.). Existing plot scripts read by path; if they
  need source-awareness later, that is a separate effort.
- Migrating existing GEOS-IT outputs. Output trees stay untouched.
- A pre-flight existence check before the date loop. Today's GEOS-IT
  path doesn't have one; adding it would be inconsistent.

## Invocation

Existing GEOS-IT runs work unchanged:

```
./run_species_optics.sh --bands sw01,sw02 --start 2008-07-01T00 --end 2008-07-01T23 --ceres
./run_external_mix.sh   --bands sw01,sw02 --start 2008-07-01T00 --end 2008-07-01T23 --ceres
./run_daily_processing.sh --start 2008-07-01 --end 2008-07-10 --detach --max-jobs 10 --ceres
```

New MERRA-2 invocations:

```
./run_species_optics.sh --source merra2 --bands sw01,sw02 \
    --start 2008-07-01T00 --end 2008-07-01T00 --ceres
./run_external_mix.sh   --source merra2 --bands sw01,sw02 \
    --start 2008-07-01T00 --end 2008-07-01T00 --ceres
./run_daily_processing.sh --source merra2 \
    --start 2008-07-01 --end 2008-07-10 --detach --max-jobs 10 --ceres
```

Notes on the MERRA-2 form:

- MERRA-2 files are daily (one file × 8 timesteps). For a single-day
  smoke test, pass `--start 2008-07-01T00 --end 2008-07-01T00` — the
  internal cadence is daily (`pd.date_range(..., freq='D')`), so one
  date enumerates one file which is processed for all 8 timesteps.
- `run_daily_processing.sh` continues to advance by 24-hour increments
  regardless of source.

## Architecture

A new module `sources.py` holds all source-specific knowledge. Both
`species_optics.py` and `external_mix.py` import from it and become
source-agnostic at the call sites.

```
sources.py
├── @dataclass(frozen=True) Source
│   ├── name                       str
│   ├── default_file_pattern       str
│   ├── cadence                    str           # pd.date_range freq
│   ├── output_subdir              str
│   ├── aer_filename_glob_suffix   str
│   ├── aer_filename_template      str
│   ├── species_glob_pattern       str
│   ├── resolve_input              Callable
│   └── build_output_name          Callable
│
├── SOURCES: dict[str, Source]                  # 'geosit', 'merra2'
└── get_source(name) -> Source                  # raises on unknown
```

`sources.py` knows nothing about optics, science, or xarray — only
filenames, paths, and cadence. `species_optics.py` and
`external_mix.py` know nothing about source-specific filename
conventions.

### Per-source field values

**GEOS-IT** — encodes today's behavior verbatim (refactor, not change):

| Field                       | Value                                                                                                  |
|-----------------------------|--------------------------------------------------------------------------------------------------------|
| `name`                      | `'geosit'`                                                                                             |
| `default_file_pattern`      | `GEOSIT/YYYY/MM/GEOS.it.asm.aer_inst_3hr_glo_L576x361_v72.GEOS5294.YYYY-MM-DDTHH00.V01.nc4`             |
| `cadence`                   | `'3h'`                                                                                                 |
| `output_subdir`             | `'GEOSIT_alpha_4'`                                                                                     |
| `aer_filename_glob_suffix`  | `'.{date}T*.V01.nc4'`                                                                                  |
| `aer_filename_template`     | `'GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.AER_{band}.{date}{ts}.V01.nc4'`                    |
| `species_glob_pattern`      | `GEOSIT_alpha_4/YYYY/MM/GEOS.it.asm.aer_inst_3hr_glo_L288x180_v24.GEOS5294.*_band.YYYY-MM-DDTHH00.V01.nc4` |
| `resolve_input(...)`        | `os.path.join(datadir, fill_date_hour_template(pattern, date_str))` — exact path, no glob              |
| `build_output_name(...)`    | Today's factored logic: remap `GEOSIT/`→`GEOSIT_alpha_4/`, then insert `<SP>_<BAND>` after `GEOS5294.` and replace `L576x361_v72`→`L288x180_v24` |

**MERRA-2** — new:

| Field                       | Value                                                                                                  |
|-----------------------------|--------------------------------------------------------------------------------------------------------|
| `name`                      | `'merra2'`                                                                                             |
| `default_file_pattern`      | `MERRA2/YYYY/MM/MERRA2_*.inst3_3d_aer_Nv.YYYYMMDD.nc4`                                                 |
| `cadence`                   | `'D'`                                                                                                  |
| `output_subdir`             | `'MERRA2_alpha_4'`                                                                                     |
| `aer_filename_glob_suffix`  | `'.{date}T*.nc4'`                                                                                      |
| `aer_filename_template`     | `'MERRA2.aer_inst_3hr_glo_L288x180_v24.AER_{band}.{date}{ts}.nc4'`                                     |
| `species_glob_pattern`      | `MERRA2_alpha_4/YYYY/MM/MERRA2.aer_inst_3hr_glo_L288x180_v24.*_band.YYYY-MM-DDTHH00.nc4`                |
| `resolve_input(...)`        | `find_file(datadir, fill_date_hour_template(pattern, date_str))` — globs `MERRA2_*` prefix; exactly one match required |
| `build_output_name(...)`    | Synthesize per-timestep: `{outdir}/MERRA2_alpha_4/YYYY/MM/MERRA2.aer_inst_3hr_glo_L288x180_v24.<SP>_<BAND>.YYYY-MM-DDTHH00.nc4` where `HH = 3 * t` |

### Worked example

For `--source merra2 --start 2008-07-01T00 --end 2008-07-01T00`,
species `SO4`, band `SW01`:

```
resolve_input → /CERES_prd/GMAO/MERRA2/2008/07/MERRA2_300.inst3_3d_aer_Nv.20080701.nc4
                (glob found exactly one file; MERRA2_300 because year=2008)

xr.open_dataset → ntime=8

t=0 → .../MERRA2_alpha_4/2008/07/MERRA2.aer_inst_3hr_glo_L288x180_v24.SO4_SW01.2008-07-01T0000.nc4
t=1 → .../MERRA2_alpha_4/2008/07/MERRA2.aer_inst_3hr_glo_L288x180_v24.SO4_SW01.2008-07-01T0300.nc4
...
t=7 → .../MERRA2_alpha_4/2008/07/MERRA2.aer_inst_3hr_glo_L288x180_v24.SO4_SW01.2008-07-01T2100.nc4
```

Eight per-timestep files written from one daily input file. Matches
the GEOS-IT output cadence for downstream consumers.

## Internals — per-file changes

### `species_optics.py`

**Argparse (near line 359), add:**

```python
parser.add_argument('--source', choices=['geosit', 'merra2'],
    default='geosit',
    help='input data source: geosit (3-hourly files) or merra2 (daily files)')
```

**`--ceres` block (lines 383-388), drop the file_pattern override:**

```python
if args.ceres:
    args.aerosol = 'aerosol_ceres.yaml'
    args.datadir = '/CERES_prd/GMAO/'
    args.outdir = '/CERES/sarb/dfillmor/'
    # REMOVED: args.file_pattern = os.path.join('GEOSIT', 'YYYY', 'MM', geos_it_filestr)
```

**Argparse default for `--file_pattern`** becomes `None` (was a hardcoded GEOS-IT string). The source-driven default kicks in below; the `None` sentinel removes the need for `parser.get_default(...)` equality checks. `--help` no longer shows a fixed default — the default is "depends on --source".

**Date loop (lines 449-463), refactor to source-driven dispatch:**

```python
src = get_source(args.source)
if args.file_pattern is None:
    args.file_pattern = src.default_file_pattern
dates = pd.date_range(start=args.start, end=args.end, freq=src.cadence)

for date in dates:
    input_path = src.resolve_input(args.datadir, args.file_pattern, date)
    ds = xr.open_dataset(input_path)
    ntime = ds['RH'].shape[0]
    for t in range(ntime):
        output_path = src.build_output_name(
            input_path, args.datadir, args.outdir,
            date, t, species_map[args.species], args.size_bin,
            band_label)
        process_file_one_timestep(
            input_path=input_path,
            output_path=output_path,
            ds=ds,
            t=t,
            ds_optics=ds_optics,
            species=species_map[args.species],
            size_bin=args.size_bin,
            band_label=band_label,
            wvl_min=wvl_min,
            wvl_max=wvl_max,
            idx_wvl=idx_wvl,
            date=date)
    ds.close()
```

**`process_file` → `process_file_one_timestep(input_path, output_path, ds, t, ...)`:**

Today's `process_file` opens the dataset and loops `for t in
range(ntime)`, building the per-timestep output filename inside via
`.replace('GEOS5294.', ...)` and `.replace('L576x361_v72', ...)`.
After the refactor:

- The dataset is opened by the caller (the date loop).
- The t-loop is also in the caller.
- The function receives the already-open `ds`, the timestep index
  `t`, and the pre-built `output_path`.
- The `.replace(...)` chain inside is removed — that logic lives in
  `Source.build_output_name`.
- `date_str` (currently `filename.split('.')[2]`, which gives `'asm'`
  for GEOS-IT — a pre-existing minor bug) becomes a parameter passed
  in as `date.strftime('%Y%m%d')`. Cleaner attrs, no regex.

### `external_mix.py`

**Argparse — same `--source` addition.**

**`--ceres` block (lines 169-171), drop the pattern remap:**

```python
if args.ceres:
    args.datadir = '/CERES/sarb/dfillmor/'
    # REMOVED: args.file_pattern = args.file_pattern.replace('GEOSIT/', 'GEOSIT_alpha_4/')
```

**Argparse default for `--file_pattern`** becomes `None` (was a
hardcoded GEOS-IT glob). Source-driven below.

**Default-pattern selection just before `pd.date_range`:**

```python
src = get_source(args.source)
if args.file_pattern is None:
    args.file_pattern = src.species_glob_pattern
dates = pd.date_range(start=args.start, end=args.end, freq=src.cadence)
```

**Note on non-CERES GEOS-IT behavior change:** today's argparse default
is `GEOSIT/YYYY/MM/...`, which without `--ceres` relies entirely on
the legacy-path fallback at lines 58-64 (which swaps to
`GEOSIT_alpha_4/`) to find files that `species_optics` actually writes
under `<outdir>/GEOSIT_alpha_4/`. After this refactor, the GEOS-IT
default is `GEOSIT_alpha_4/YYYY/MM/...` directly — the legacy fallback
becomes redundant for fresh runs but stays for any pre-existing output
trees still rooted at `GEOSIT/`.

**Legacy fallback (lines 58-64)** — kept for GEOS-IT only. MERRA-2 has
no legacy paths.

### `run_species_optics.sh`, `run_external_mix.sh`

Add `--source SOURCE` to the wrapper's own argparse loop (default
`geosit`). Document it in `usage()`. Forward as `--source "$SOURCE"`
to the Python invocation.

### `run_daily_processing.sh`

Three touch-points beyond just passing the flag through:

1. **Argparse**: add `--source SOURCE` (default `geosit`) and push it
   into `EXTRA_ARGS` so it flows to both sub-wrappers.

2. **`SKIP_SUBDIR` resolution (lines 158-178)**:

   ```bash
   case "$SOURCE" in
       merra2) SKIP_SUBDIR_DEFAULT="MERRA2"; SKIP_SUBDIR_CERES="MERRA2_alpha_4" ;;
       geosit) SKIP_SUBDIR_DEFAULT="GEOSIT"; SKIP_SUBDIR_CERES="GEOSIT_alpha_4" ;;
   esac
   ```

   The existing `--ceres` / `--workdir` loop then picks `_CERES` vs
   `_DEFAULT`.

3. **`is_day_complete` glob (lines 188-189)**:

   ```bash
   case "$SOURCE" in
       merra2) AER_GLOB_SUFFIX=".${day_date}T*.nc4" ;;
       geosit) AER_GLOB_SUFFIX=".${day_date}T*.V01.nc4" ;;
   esac
   n_sw=$(find "$outdir" -maxdepth 1 -type f -name "*AER_SW*${AER_GLOB_SUFFIX}" ...)
   n_lw=$(find "$outdir" -maxdepth 1 -type f -name "*AER_LW*${AER_GLOB_SUFFIX}" ...)
   ```

### `check_aer_grid.py`

Source-aware `subdir` (line 50) and filename template (lines 55-56):

```python
src = get_source(args.source)
subdir = src.output_subdir
filename_tpl = src.aer_filename_template
```

The `T0000.V01.nc4` → `T*.V01.nc4` glob substitution at line 407
becomes a source-aware suffix swap using `src.aer_filename_glob_suffix`.

Add `--source` to argparse alongside `--ceres`. Help text on line 334
updated to drop the `(GEOSIT_alpha_4)` mention.

### `kill_daily_jobs.sh`

No changes — it signals PIDs from the pidfile and has no
source-specific strings.

## Error handling

The new failure modes are all in `sources.py`:

| Failure                                                  | Where               | Behavior                                                                                              |
|----------------------------------------------------------|---------------------|-------------------------------------------------------------------------------------------------------|
| Unknown `--source` value                                 | argparse `choices`  | argparse rejects at parse time with the standard error.                                               |
| `--source merra2` but glob finds zero files for a day    | `utils.find_file`   | Raises `Exception('no file matches for %s')` (existing behavior); the daily wrapper logs the day as failed. |
| `--source merra2` but glob finds >1 files for a day      | `utils.find_file`   | Raises `Exception('more than one file match %s')`. Surfaces stream-prefix ambiguity early.            |
| User passes `--file_pattern` that doesn't match source   | not validated       | Honored as-is (escape hatch). If it points at the wrong tree, downstream `xr.open_dataset` fails with a clear `FileNotFoundError`. |
| MERRA-2 file missing expected variables (RH/DELP/PS/...) | `xr.open_dataset`   | Standard xarray `KeyError` propagates. Same as today for GEOS-IT.                                     |
| `--ceres` + `--source merra2`                            | n/a                 | No conflict — `aerosol_ceres.yaml` already references MERRA-2 optics.                                 |

## Testing strategy

The repo has no existing test suite; "testing" here means a layered
verification plan, not pytest-as-CI.

**1. Unit tests** (new — `tests/test_sources.py`). Pure string-in /
string-out; no I/O, no xarray. Runs in <1s.

- `test_geosit_default_pattern_matches_today` — verifies the GEOS-IT
  `default_file_pattern` is byte-identical to today's hardcoded
  string in `species_optics.py`. Locks in the refactor.
- `test_geosit_build_output_name_matches_today_logic` — feed it a
  sample input path + (date, t=0, species='SO4', band='SW01') and
  assert the output matches what today's `.replace(...)` chain
  produces. Locks in equivalence.
- `test_merra2_build_output_name_eight_timesteps` — call with t=0..7,
  assert HH values 00/03/06/.../21 and the path tree
  `MERRA2_alpha_4/2008/07/`.
- `test_merra2_resolve_input_globs_stream_prefix` — monkeypatch
  `utils.find_file` to capture and return; assert the pattern passed
  in contains `MERRA2_*` (not a hardcoded stream number).
- `test_unknown_source_raises` — `get_source('geosfp')` raises with a
  message that lists the valid sources.

**2. GEOS-IT regression check** (manual but reproducible). Run a
recent already-processed GEOS-IT day with the new code and `diff` the
subsampled outputs against the existing baseline under
`/CERES/sarb/dfillmor/GEOSIT_alpha_4/`. The refactor must produce
byte-identical outputs for the GEOS-IT path.

**3. MERRA-2 smoke test** — process 2008-07-01 (MERRA-2 files exist
at `/CERES_prd/GMAO/MERRA2/2008/07/MERRA2_300.inst3_3d_aer_Nv.20080701.nc4`)
for `sw01,lw01` and verify:

- 8 timesteps × N species per band end up under
  `MERRA2_alpha_4/2008/07/` with names matching the template.
- `external_mix` produces 8 `AER_SW01` and 8 `AER_LW01` files.
- `check_aer_grid.py --source merra2 --date 2008-07-01 --bands sw01,lw01 --ceres`
  produces a sane AOD map (global mean within ~0.05–0.5; not zero,
  not NaN; columns elevated over Sahara and East Asia).

## Estimated diff size

- `sources.py` + `tests/test_sources.py`: ~150 LOC added.
- GEOS-IT-specific bits factored out: ~30 LOC removed.
- Modified across wrappers and Python scripts: ~50 LOC.

Net: small, contained, no science changes.
