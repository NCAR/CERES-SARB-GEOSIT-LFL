import unittest
import os
import pandas as pd
from unittest.mock import patch

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


if __name__ == '__main__':
    unittest.main()
