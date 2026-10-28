import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import server


class FalRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_key = os.environ.pop("UNIFICALLY_API_KEY", None)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        if cls.old_key is not None:
            os.environ["UNIFICALLY_API_KEY"] = cls.old_key

    def test_provider_status_never_returns_the_secret(self):
        with urllib.request.urlopen(self.base + "/api/fal/status") as response:
            data = json.load(response)
        self.assertIn("configured", data)
        self.assertNotIn("UNIFICALLY_API_KEY", json.dumps(data))

    def test_estimate_endpoint_returns_cost_without_submitting_a_job(self):
        with urllib.request.urlopen(self.base + "/api/fal/estimate?duration=10") as response:
            data = json.load(response)
        self.assertEqual(data["estimated_cost_usd"], "1.134")
        self.assertEqual(data["model"], "kuaishou/kling-4.0-video")

    def test_generation_requires_login(self):
        body = json.dumps({"duration": 10, "image_data_url": "x"}).encode("utf-8")
        request = urllib.request.Request(
            self.base + "/api/generations", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 401)
        caught.exception.close()

    def test_projects_and_payments_require_login(self):
        for path in ("/api/projects", "/api/users/me"):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(self.base + path)
            self.assertEqual(caught.exception.code, 401, path)
            caught.exception.close()
        body = json.dumps({"package_id": "720p-5-1", "user_id": "someone-else"}).encode("utf-8")
        request = urllib.request.Request(
            self.base + "/api/icount/create-payment", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 401)
        caught.exception.close()

    def test_generation_requires_configured_key_and_valid_payload(self):
        body = json.dumps({"approved_cost": True, "duration": 10}).encode("utf-8")
        request = urllib.request.Request(
            self.base + "/api/generations",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 401)
        raw_error = caught.exception.read()
        caught.exception.close()
        error = json.loads(raw_error)
        self.assertIn("error", error)


if __name__ == "__main__":
    unittest.main()
