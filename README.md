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
- `--ceres` - Use CERES data paths
- `--datadir DIR` - Custom data directory

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
