# CERES-SARB-GEOSIT-LFL
Python scripts for GEOSIT LFL pre-processing.

## Environment Setup

Create the conda environment using conda-forge:

```bash
conda create -n sarb -c conda-forge python numpy xarray pandas scipy cartopy matplotlib pyyaml netcdf4
```

Activate the environment:

```bash
conda activate sarb
```

## Batch Processing

### Single Band Processing

Run species optics and external mixing for specific bands:

```bash
./run_species_optics.sh --bands sw01,sw02 --start 2008-07-01T00 --end 2008-07-01T23 --ceres
./run_external_mix.sh --bands sw01,sw02 --start 2008-07-01T00 --end 2008-07-01T23 --ceres
```

Other users running on CERES machines should add `--workdir` and `--optics-dir`.
First unpack the optics tarball into your workspace:

```bash
cd /CERES/sarb/myuser/
tar xf /CERES/sarb/dfillmor/Optics.tar
```

Then run with both flags:

```bash
./run_species_optics.sh --bands sw01,sw02 --start 2008-07-01T00 --end 2008-07-01T23 \
    --ceres --workdir /CERES/sarb/myuser/ --optics-dir /CERES/sarb/myuser/Optics
./run_external_mix.sh --bands sw01,sw02 --start 2008-07-01T00 --end 2008-07-01T23 \
    --ceres --workdir /CERES/sarb/myuser/
```

### Daily Processing Pipeline

`run_daily_processing.sh` orchestrates batch processing across date ranges, launching one background job per day:

```bash
./run_daily_processing.sh --start 2008-07-01 --end 2008-07-10 --detach --max-jobs 10 --ceres
```

**Options:**
- `--start DATE` / `--end DATE` - Date range in YYYY-MM-DD format (required)
- `--detach` - Exit after launching jobs (don't wait for completion)
- `--max-jobs N` - Limit concurrent background jobs (default: unlimited)
- `--logdir DIR` - Directory for log files (default: `./logs`)
- `--dry-run` - Preview what would run without executing
- `--ceres` - Use CERES production data paths
- `--workdir DIR` - Workspace directory for output files (default with `--ceres`: `/CERES/sarb/dfillmor/`); other users should set this to `/CERES/sarb/<username>/`
- `--optics-dir DIR` - Optics data directory (default with `--ceres`: `/CERES/sarb/dfillmor/Optics`); other users should point this at their unpacked copy of `Optics.tar`
- `--datadir DIR` - Custom input data directory

Each day's output is logged to `logs/processing_YYYY-MM-DD.log`.

### Running Jobs That Survive Logout

Background jobs will be killed when you log out unless you use one of these methods:

**Option 1: Wrap with nohup**
```bash
nohup ./run_daily_processing.sh --start 2008-07-01 --end 2008-07-10 --detach --max-jobs 10 --ceres > run.log 2>&1 &
```

**Option 2: Use screen or tmux (recommended)**
```bash
screen -S processing
./run_daily_processing.sh --start 2008-07-01 --end 2008-07-10 --detach --max-jobs 10 --ceres
# Ctrl-A, D to detach from screen
# screen -r processing to reattach later
```

### Monitoring and Managing Jobs

Check job status:
```bash
./kill_daily_jobs.sh --status
```

Monitor logs:
```bash
tail -f logs/processing_*.log
```

Kill all running jobs:
```bash
./kill_daily_jobs.sh
```

Force kill (SIGKILL):
```bash
./kill_daily_jobs.sh --force
```

### Quick QC (per-band regional means)

For a fast text-only sanity check of AER output on bands that have
finished, use `check_aer_grid.py`. It writes two files per (band, window)
under `--outdir`:

- `aer_check_{BAND}_{window}.txt` — global stats and a 9×18
  area-weighted regional-mean map of column AOD.
- `aer_mean_{BAND}_{window}.nc` — the full-resolution 180×288
  time-mean field of `Extinction_Column_Optical_Depth`.

`{window}` is `YYYY-MM-DD` for a single day or
`YYYY-MM-DD_to_YYYY-MM-DD` for a range.

Single-day:
```bash
./check_aer_grid.py --date 2008-07-01 --bands sw01,sw02 --ceres
cat qc/aer_check_SW01_2008-07-01.txt
```

Date range (inclusive on both ends):
```bash
./check_aer_grid.py --date-begin 2008-07-01 --date-end 2008-07-31 \
    --bands sw01 --ceres
cat qc/aer_check_SW01_2008-07-01_to_2008-07-31.txt
ncdump -h qc/aer_mean_SW01_2008-07-01_to_2008-07-31.nc
```

Other users on CERES machines should add `--workdir`:
```bash
./check_aer_grid.py --date 2008-07-01 --bands sw01,sw02 \
    --ceres --workdir /CERES/sarb/myuser/
```

`--date` is mutually exclusive with `--date-begin`/`--date-end`. The
range form averages every available timestep file with equal weight (a
day with missing timesteps contributes proportionally less to the mean).

Bands can be listed in any combination (`sw01,sw02,lw03,...`). The script
exits non-zero only if a requested band has zero timestep files across
the entire window.

When stdout is a TTY the colorized map is also printed to the terminal
(blue for clean, green/yellow for moderate, orange/red for heavy AOD).
Use `--no-color` to suppress, or `--color` to force on when piped.
