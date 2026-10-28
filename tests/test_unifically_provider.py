import unittest
from decimal import Decimal
from unittest import mock

import unifically_provider as uni


class UnifiallyProviderTests(unittest.TestCase):
    def test_1080p_costs_one_and_a_half_times_720p(self):
        self.assertEqual(uni.RATE_PER_SECOND_USD["1080p"], uni.RATE_PER_SECOND_USD["720p"] * Decimal("1.5"))

    def test_generation_maps_resolution_to_mode_and_returns_video_url(self):
        calls = []

        def fake_request(method, path, body=None):
            calls.append((method, path, body))
            if method == "POST":
                return {"data": {"task_id": "t1", "status": "processing"}}
            return {"data": {"task_id": "t1", "status": "completed", "output": {"video_url": "https://cdn.example.com/v.mp4"}}}

        with mock.patch.object(uni, "_request", side_effect=fake_request):
            url = uni.generate_clip(image_url="https://clipik.pro/uploads/a.jpg", prompt="p", duration=10,
                                    resolution="1080p", platform="רחב · 16:9", poll_interval=0, timeout=5)
        self.assertEqual(url, "https://cdn.example.com/v.mp4")
        post_body = calls[0][2]
        self.assertEqual(post_body["model"], "kuaishou/kling-4.0-video")
        self.assertEqual(post_body["input"]["mode"], "pro")
        self.assertEqual(post_body["input"]["aspect_ratio"], "16:9")
        self.assertEqual(post_body["input"]["image_urls"], ["https://clipik.pro/uploads/a.jpg"])

    def test_failed_task_raises_user_visible_error(self):
        responses = [{"data": {"task_id": "t2"}}, {"data": {"status": "failed", "error_message": "bad image"}}]
        with mock.patch.object(uni, "_request", side_effect=responses):
            with self.assertRaises(uni.UnifiError) as ctx:
                uni.generate_clip(image_url="https://clipik.pro/uploads/a.jpg", prompt="p", duration=5,
                                  poll_interval=0, timeout=5)
        self.assertIn("bad image", str(ctx.exception))

    def test_rejects_non_public_image_url(self):
        with self.assertRaises(uni.UnifiError):
            uni.generate_clip(image_url="http://127.0.0.1/a.jpg", prompt="p", duration=5)


if __name__ == "__main__":
    unittest.main()
