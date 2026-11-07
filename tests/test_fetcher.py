"""
Unit tests for the fetcher module.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import requests

from fetcher import download_cover_image, fetch_page, sleep_with_jitter


class TestFetcher(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
    def test_sleep_with_jitter(self):
        with patch("time.sleep") as mock_sleep:
            duration = sleep_with_jitter(base_delay=2.0, jitter=0.5)
            self.assertGreaterEqual(duration, 1.5)
            self.assertLessEqual(duration, 2.5)
            mock_sleep.assert_called_once_with(duration)

    def test_sleep_with_jitter_zero(self):
        duration = sleep_with_jitter(base_delay=0.0)
        self.assertEqual(duration, 0.0)

    def test_fetch_page_success(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Hello Novel</body></html>"
        mock_session.get.return_value = mock_response

        content = fetch_page("https://example.com/ch/1", session=mock_session)
        self.assertEqual(content, "<html><body>Hello Novel</body></html>")
        self.assertEqual(mock_response.encoding, "utf-8")
        self.assertEqual(mock_session.get.call_count, 1)

    @patch("time.sleep")
    def test_fetch_page_retry_on_500(self, mock_sleep):
        mock_session = MagicMock()

        # Fail once with 500, then succeed
        err_response = requests.Response()
        err_response.status_code = 500
        http_err = requests.exceptions.HTTPError(response=err_response)

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.text = "<html>Recovered</html>"

        mock_session.get.side_effect = [http_err, success_response]

        content = fetch_page(
            "https://example.com/ch/1",
            session=mock_session,
            max_retries=3,
            retry_backoff=1.0,
        )
        self.assertEqual(content, "<html>Recovered</html>")
        self.assertEqual(mock_session.get.call_count, 2)
        mock_sleep.assert_called_once_with(1.0)

    @patch("time.sleep")
    def test_fetch_page_404_no_retry(self, mock_sleep):
        mock_session = MagicMock()
        err_response = requests.Response()
        err_response.status_code = 404
        http_err = requests.exceptions.HTTPError(response=err_response)
        mock_session.get.side_effect = http_err

        with self.assertRaises(requests.exceptions.HTTPError):
            fetch_page("https://example.com/ch/999", session=mock_session, max_retries=3)

        self.assertEqual(mock_session.get.call_count, 1)
        mock_sleep.assert_not_called()

    def test_fetch_json_success(self):
        from fetcher import fetch_json

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok", "content": "<div>test</div>"}
        mock_session.get.return_value = mock_response

        data = fetch_json("https://novelight.net/api/test", session=mock_session)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(mock_session.get.call_count, 1)

        # Check headers passed to get
        args, kwargs = mock_session.get.call_args
        self.assertIn("headers", kwargs)
        self.assertEqual(kwargs["headers"].get("X-Requested-With"), "XMLHttpRequest")

    def test_fetch_json_with_params(self):
        from fetcher import fetch_json

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"chapters": []}
        mock_session.get.return_value = mock_response

        params = {"book_id": "337", "page": 1}
        data = fetch_json(
            "https://novelight.net/book/ajax/chapter-pagination",
            params=params,
            session=mock_session,
        )
        self.assertEqual(data["chapters"], [])
        args, kwargs = mock_session.get.call_args
        self.assertEqual(kwargs["params"], params)

    def test_download_cover_image_empty_or_invalid_url(self):
        self.assertIsNone(download_cover_image("", self.test_dir))
        self.assertIsNone(download_cover_image(None, self.test_dir))
        self.assertIsNone(download_cover_image("   ", self.test_dir))

    def test_download_cover_image_success_default_jpg(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\xff\xd8\xff\xe0fake-jpeg-binary"
        mock_resp.headers = {"Content-Type": "image/jpeg"}
        mock_session.get.return_value = mock_resp

        cover_path = download_cover_image(
            "https://novelight.net/media/book/poster/dragon.jpg",
            dest_dir=self.test_dir,
            session=mock_session,
        )
        expected_path = os.path.join(self.test_dir, "cover.jpg")
        self.assertEqual(cover_path, expected_path)
        self.assertTrue(os.path.exists(expected_path))
        with open(expected_path, "rb") as f:
            self.assertEqual(f.read(), b"\xff\xd8\xff\xe0fake-jpeg-binary")

    def test_download_cover_image_content_type_png(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\x89PNGfake-png-binary"
        mock_resp.headers = {"Content-Type": "image/png"}
        mock_session.get.return_value = mock_resp

        cover_path = download_cover_image(
            "https://fenrirealm.com/media/covers/novel-cover",
            dest_dir=self.test_dir,
            session=mock_session,
        )
        expected_path = os.path.join(self.test_dir, "cover.png")
        self.assertEqual(cover_path, expected_path)
        self.assertTrue(os.path.exists(expected_path))

    def test_download_cover_image_caching(self):
        existing_cover = os.path.join(self.test_dir, "cover.jpg")
        with open(existing_cover, "wb") as f:
            f.write(b"cached-cover-data")

        mock_session = MagicMock()
        cover_path = download_cover_image(
            "https://example.com/cover.jpg",
            dest_dir=self.test_dir,
            session=mock_session,
            force=False,
        )
        self.assertEqual(cover_path, existing_cover)
        mock_session.get.assert_not_called()

    def test_download_cover_image_force_overwrites_cache(self):
        existing_cover = os.path.join(self.test_dir, "cover.jpg")
        with open(existing_cover, "wb") as f:
            f.write(b"old-data")

        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"new-data"
        mock_resp.headers = {"Content-Type": "image/jpeg"}
        mock_session.get.return_value = mock_resp

        cover_path = download_cover_image(
            "https://example.com/cover.jpg",
            dest_dir=self.test_dir,
            session=mock_session,
            force=True,
        )
        self.assertEqual(cover_path, existing_cover)
        with open(existing_cover, "rb") as f:
            self.assertEqual(f.read(), b"new-data")
        mock_session.get.assert_called_once()

    def test_download_cover_image_rejects_html(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"<html><head><title>404 Not Found</title></head></html>"
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_session.get.return_value = mock_resp

        cover_path = download_cover_image(
            "https://example.com/cover.jpg",
            dest_dir=self.test_dir,
            session=mock_session,
        )
        self.assertIsNone(cover_path)
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "cover.jpg")))

    @patch("time.sleep")
    def test_download_cover_image_network_failure(self, mock_sleep):
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        cover_path = download_cover_image(
            "https://example.com/cover.jpg",
            dest_dir=self.test_dir,
            session=mock_session,
            max_retries=2,
            retry_backoff=0.01,
        )
        self.assertIsNone(cover_path)

    def test_download_cover_image_browser_fallback(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_session.get.return_value = mock_resp

        mock_browser_ctx = MagicMock()
        mock_playwright_resp = MagicMock()
        mock_playwright_resp.ok = True
        mock_playwright_resp.body.return_value = b"browser-downloaded-bytes"
        mock_playwright_resp.headers = {"content-type": "image/jpeg"}
        mock_browser_ctx.request.get.return_value = mock_playwright_resp

        with patch("fenrirealm.fetcher._context", mock_browser_ctx):
            cover_path = download_cover_image(
                "https://fenrirealm.com/media/covers/cf-protected.jpg",
                dest_dir=self.test_dir,
                session=mock_session,
            )
            self.assertIsNotNone(cover_path)
            self.assertTrue(os.path.exists(cover_path))
            with open(cover_path, "rb") as f:
                self.assertEqual(f.read(), b"browser-downloaded-bytes")


if __name__ == "__main__":
    unittest.main()

