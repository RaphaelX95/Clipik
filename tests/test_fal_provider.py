import base64
import unittest
from decimal import Decimal

from fal_provider import build_prompt, fit_image_to_platform, partition_script, split_duration, validate_image_data_url
from unifically_provider import estimate_cost_usd, estimate_tokens


class FalProviderTests(unittest.TestCase):
    def test_splits_supported_video_lengths_into_model_sized_clips(self):
        self.assertEqual(split_duration(10), [10])
        self.assertRaises(ValueError, split_duration, 2)
        self.assertRaises(ValueError, split_duration, 2)
        self.assertRaises(ValueError, split_duration, 2)
        self.assertRaises(ValueError, split_duration, 2)

    def test_rejects_fractional_duration_instead_of_rounding_it(self):
        with self.assertRaises(ValueError):
            split_duration(15.5)

    def test_estimates_unifically_cost_per_resolution(self):
        self.assertEqual(estimate_cost_usd(10), Decimal("1.134"))
        self.assertEqual(estimate_cost_usd(10, "1080p"), Decimal("1.701"))
        self.assertEqual(estimate_cost_usd(5), Decimal("0.567"))

    def test_rejects_unknown_resolution(self):
        with self.assertRaises(ValueError):
            estimate_cost_usd(10, "4k")

    def test_fits_uploaded_image_to_selected_output_ratio(self):
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+cVuoAAAAASUVORK5CYII=")
        content_type, fitted = fit_image_to_platform(png, "ריבוע · 1:1")
        self.assertEqual(content_type, "image/png")
        self.assertEqual((int.from_bytes(fitted[16:20], "big"), int.from_bytes(fitted[20:24], "big")), (1024, 1024))

    def test_accepts_a_valid_jpeg_data_url(self):
        raw = b"jpeg bytes"
        encoded = base64.b64encode(raw).decode("ascii")
        content_type, decoded = validate_image_data_url(f"data:image/jpeg;base64,{encoded}")
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(decoded, raw)

    def test_rejects_non_image_data_urls(self):
        with self.assertRaises(ValueError):
            validate_image_data_url("data:text/html;base64,PGh0bWw+")

    def test_rejects_invalid_base64(self):
        with self.assertRaises(ValueError):
            validate_image_data_url("data:image/png;base64,%%%bad%%")

    def test_partitions_spoken_script_without_repeating_it(self):
        chunks = partition_script("פתיח ראשון. המוצר הזה מתאים לי. נסיים בקריאה לפעולה!", 2)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(" ".join(chunks), "פתיח ראשון. המוצר הזה מתאים לי. נסיים בקריאה לפעולה!")

    def test_estimate_tokens(self):
        self.assertEqual(estimate_tokens(5), 2)
        self.assertEqual(estimate_tokens(10), 4)
        self.assertEqual(estimate_tokens(15), 6)
        self.assertEqual(estimate_tokens(20), 8)
        self.assertEqual(estimate_tokens(25), 10)
        self.assertEqual(estimate_tokens(30), 12)
        self.assertEqual(estimate_tokens(15, "1080p"), 9)

    def test_voiceover_mode_requests_product_shots_not_a_talking_head(self):
        prompt = build_prompt(
            product="בקבוק תרמי", audience="", language="עברית", script="שומרים על המשקה חם.",
            style="קריינות ותקריבים", creator="קריינות", segment_index=0, segment_count=1,
        )
        self.assertIn("תמונות מוצר קרובות", prompt)
        self.assertIn("קריינות טבעית", prompt)

    def test_prompt_preserves_product_and_spoken_script(self):
        prompt = build_prompt(
            product="בקבוק תרמי",
            audience="מטיילים",
            language="עברית",
            script="הכירו את הבקבוק ושמרו על המשקה חם.",
            style="UGC טבעי",
            segment_index=0,
            segment_count=1,
        )
        self.assertIn("בקבוק תרמי", prompt)
        # RTL scripts are reversed to counteract model reversal
        reversed_script = "הכירו את הבקבוק ושמרו על המשקה חם."[::-1]
        self.assertIn(reversed_script, prompt)
        self.assertIn("עברית", prompt)
        self.assertIn("אל תשנה", prompt)


if __name__ == "__main__":
    unittest.main()
