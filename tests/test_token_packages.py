import unittest
from decimal import Decimal

import token_packages as tp


class TokenPackagesTest(unittest.TestCase):
    def test_single_720p_15s_price_and_tokens(self):
        q = tp.quote("720p", 15, 1)
        self.assertEqual(q["tokens"], 6)
        self.assertEqual(q["price_ils"], Decimal("8.80"))

    def test_promo_applies_to_1080p_30s_only(self):
        self.assertEqual(tp.quote("1080p", 30, 5)["price_ils"], Decimal("112.23"))
        self.assertEqual(tp.quote("1080p", 30, 20)["price_ils"], Decimal("448.94"))
        self.assertEqual(tp.quote("720p", 30, 5)["promo_discount"], Decimal("0"))

    def test_pack_tokens_scale_with_count(self):
        self.assertEqual(tp.quote("1080p", 15, 10)["tokens"], 90)

    def test_lookup_rejects_unknown_ids(self):
        self.assertIsNone(tp.lookup("bogus"))
        self.assertIsNone(tp.lookup("720p-15-7"))
        self.assertIsNone(tp.lookup("720p-12-5"))
        self.assertEqual(tp.lookup("trial")["price_ils"], Decimal("9.99"))

    def test_catalog_has_every_type_and_size(self):
        self.assertEqual(len(tp.catalog()), len(tp.VIDEO_TYPES) * len(tp.VIDEO_COUNTS))


if __name__ == "__main__":
    unittest.main()
