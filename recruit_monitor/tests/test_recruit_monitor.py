import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import recruit_monitor


class HeaderTests(unittest.TestCase):
    def test_default_headers_do_not_request_brotli(self):
        headers = recruit_monitor.default_headers()

        self.assertEqual(headers["Accept-Encoding"], "gzip, deflate")
        self.assertNotIn("br", headers["Accept-Encoding"])


if __name__ == "__main__":
    unittest.main()
