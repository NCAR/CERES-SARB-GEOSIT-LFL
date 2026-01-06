# Project: CERES-SARB-GEOSIT-LFL

Scientific data processing pipeline for aerosol optical properties. Prepares GEOS-IT atmospheric data for the CERES mission's SARB module using the Langley-Fu-Liou (LFL) radiative transfer model.

## Environment

Use the `sarb` conda environment for all Python commands:

```bash
source ~/miniconda3/etc/profile.d/conda.sh && conda activate sarb
```

## Key Files

- `species_optics.py` - Core processing: RH interpolation, extinction/scattering calculations
- `external_mix.py` - Combines multiple aerosol species into aggregate files
- `plot_geosit.py` - Visualization of extinction column optical depth
- `utils.py` - Utility functions (date templates, file discovery)
- `aerosol.yaml` / `aerosol_ceres.yaml` - Aerosol species configuration
- `bands.yaml` - Spectral band definitions
- `run_species_optics.sh` / `run_external_mix.sh` - Batch execution scripts
