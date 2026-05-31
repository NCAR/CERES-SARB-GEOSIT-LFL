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
