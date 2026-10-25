"""
Unit tests for the fetcher module.
"""

import unittest
from unittest.mock import MagicMock, patch

import requests

from fetcher import fetch_page, sleep_with_jitter


class TestFetcher(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

