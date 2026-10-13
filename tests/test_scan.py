import json
import os
import tempfile
import unittest

from ws_sunset.scan import main, scan, scan_text


def kinds(text, path="x.py"):
    return [f.kind for f in scan_text(path, text)]


class ScanText(unittest.TestCase):
    def test_iv_url_maps_to_continuous(self):
        f = scan_text("a.py", 'u = "https://waterservices.usgs.gov/nwis/iv/?sites=01646500&format=json"')
        self.assertEqual([x.kind for x in f], ["legacy-endpoint"])
        self.assertIn("collections/continuous", f[0].replacement)
        self.assertIn("latest-continuous", f[0].replacement)
        self.assertTrue(f[0].guide.endswith("#migrating-from-%2Fiv-to-%2Fcontinuous"))

    def test_each_documented_endpoint(self):
        want = {"dv": "daily", "site": "monitoring-locations", "gwlevels": "field-measurements",
                "measurements": "field-measurements", "peak": "peaks", "stat": "statistics", "qwdata": "samples"}
        for ep, frag in want.items():
            f = scan_text("a.py", f"https://waterservices.usgs.gov/nwis/{ep}/?x=1")
            self.assertEqual(len(f), 1, ep)
            self.assertIn(frag, f[0].replacement, ep)

    def test_waterdata_nwis_peak_page(self):
        self.assertEqual(kinds("https://waterdata.usgs.gov/nwis/peak?site_no=1"), ["legacy-endpoint"])

    def test_bare_host_without_known_endpoint(self):
        self.assertEqual(kinds("BASE = 'https://waterservices.usgs.gov/'"), ["legacy-host"])

    def test_new_api_is_not_flagged(self):
        self.assertEqual(kinds("https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items"), [])

    def test_r_readnwis(self):
        self.assertEqual(kinds("q <- readNWISuv(site, '00060')", "a.R"), ["r-dataRetrieval"])
        self.assertEqual(kinds("x <- whatNWISdata(siteNumber = s)", "a.R"), ["r-dataRetrieval"])

    def test_python_nwis_module(self):
        self.assertEqual(kinds("from dataretrieval import nwis"), ["py-dataretrieval"])
        self.assertEqual(kinds("df, md = nwis.get_iv(sites='01646500')"), ["py-dataretrieval"])
        self.assertEqual(kinds("from dataretrieval import waterdata"), [])

    def test_legacy_provisional_checks(self):
        for line in ["if 'P' in v['qualifiers']:", 'provisional = "P" in value.qualifiers',
                     "if (v.qualifiers.includes('P')) {", "keep <- qualifiers %in% 'P'",
                     "if 'P' not in rec['qualifiers']:"]:
            self.assertIn("provisional-check", kinds(line), line)

    def test_qualifiers_field_only_with_legacy_context(self):
        legacy = 'u = "https://waterservices.usgs.gov/nwis/iv/"\nq = item.get("qualifiers", [])'
        self.assertIn("qualifiers-field", kinds(legacy))
        self.assertNotIn("qualifiers-field", kinds('q = item.get("qualifiers", [])'))

    def test_rdb_cd_column(self):
        self.assertIn("rdb-cd-column", kinds("df['X_00060_cd'] == 'P'"))

    def test_unrelated_code_is_quiet(self):
        self.assertEqual(kinds("qualifiers = []\nprint('Pending')\nx_cd = 1"), [])


class Files(unittest.TestCase):
    def test_notebook_and_skips(self):
        with tempfile.TemporaryDirectory() as d:
            nb = {"cells": [{"source": ["import dataretrieval.nwis as nwis\n", "nwis.get_dv(sites='1')"]}]}
            open(os.path.join(d, "n.ipynb"), "w").write(json.dumps(nb))
            os.makedirs(os.path.join(d, "node_modules"))
            open(os.path.join(d, "node_modules", "dep.js"), "w").write("https://waterservices.usgs.gov/nwis/iv/")
            open(os.path.join(d, "img.png"), "w").write("https://waterservices.usgs.gov/nwis/iv/")
            found = scan([d])
            self.assertEqual({os.path.basename(f.path) for f in found}, {"n.ipynb"})
            self.assertEqual([f.line for f in found], [1, 2])

    def test_exit_code_and_json(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(main([d]), 0)
            open(os.path.join(d, "a.py"), "w").write("https://waterservices.usgs.gov/nwis/dv/")
            self.assertEqual(main([d, "--json"]), 1)


if __name__ == "__main__":
    unittest.main()
