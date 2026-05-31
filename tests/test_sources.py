import unittest
import os
import pandas as pd

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


if __name__ == '__main__':
    unittest.main()
