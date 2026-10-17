import unittest
from types import SimpleNamespace
from unittest.mock import patch

from starlette.routing import Match

import backend.main as main
import backend.news as news
from backend.signals import classify_article
from backend.simulator import Portfolio, run_backtest


class LiveNewsRouteTests(unittest.TestCase):
    def test_live_news_parses_provider_articles(self):
        news._live_cache = None
        response = unittest.mock.Mock()
        response.status_code = 200
        response.headers = {}
        response.json.return_value = {
            "articles": [
                {
                    "title": "Test headline",
                    "source": {"name": "Test source"},
                    "publishedAt": "2026-10-17T00:00:00Z",
                    "url": "https://example.test/article",
                    "description": "Test description",
                }
            ]
        }
        with patch.object(news, "API_KEY", "test-key"), patch.object(
            news.requests, "get", return_value=response
        ) as request:
            articles = news.get_live_news()

        request.assert_called_once()
        self.assertEqual(articles[0]["title"], "Test headline")
        self.assertEqual(articles[0]["source"], "Test source")

    def test_live_news_deduplicates_canonical_urls_and_rejects_unsafe_links(self):
        news._live_cache = None
        response = unittest.mock.Mock()
        response.status_code = 200
        response.headers = {}
        response.json.return_value = {
            "articles": [
                {"title": "First story", "source": {"name": "Source"}, "url": "https://EXAMPLE.test/story?utm_source=a#top"},
                {"title": "Duplicate story", "source": {"name": "Source"}, "url": "https://example.test/story?utm_source=b"},
                {"title": "Unsafe story", "source": {"name": "Source"}, "url": "javascript:alert(1)"},
            ]
        }
        with patch.object(news, "API_KEY", "test-key"), patch.object(news.requests, "get", return_value=response):
            articles = news.get_live_news()

        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0]["url"], "https://example.test/story")
        self.assertIsNone(articles[1]["url"])

    def test_live_news_rejects_non_object_provider_json(self):
        news._live_cache = None
        response = unittest.mock.Mock()
        response.status_code = 200
        response.headers = {}
        response.json.return_value = ["unexpected", "list"]
        with patch.object(news, "API_KEY", "test-key"), patch.object(
            news.requests, "get", return_value=response
        ):
            with self.assertRaises(ValueError):
                news.get_live_news()

    def test_missing_api_key_maps_to_503(self):
        with patch.object(
            main,
            "get_live_news",
            side_effect=RuntimeError("NEWS_API_KEY is missing."),
        ):
            with self.assertRaises(main.HTTPException) as raised:
                main.read_live_news(SimpleNamespace(client=SimpleNamespace(host="unit-missing", headers={})))

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail, "NEWS_API_KEY is missing.")

    def test_provider_connection_error_maps_to_502(self):
        from requests.exceptions import ConnectionError

        with patch.object(main, "get_live_news", side_effect=ConnectionError()):
            with self.assertRaises(main.HTTPException) as raised:
                main.read_live_news(SimpleNamespace(client=SimpleNamespace(host="unit-connection", headers={})))

        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(
            raised.exception.detail,
            "The external news provider could not be reached.",
        )

    def test_live_news_path_uses_live_handler(self):
        scope = {
            "type": "http",
            "path": "/api/news/live",
            "root_path": "",
            "method": "GET",
            "headers": [],
        }
        matched_route = next(
            route
            for route in main.app.router.routes
            if route.matches(scope)[0] is Match.FULL
        )

        with patch.object(main, "get_live_news", return_value=[{"title": "Test"}]) as provider:
            result = matched_route.endpoint(SimpleNamespace(client=SimpleNamespace(host="unit-route"), headers={}))

        self.assertIs(matched_route.endpoint, main.read_live_news)
        provider.assert_called_once_with()
        self.assertEqual(result, [{"title": "Test"}])


class SimulationTests(unittest.TestCase):
    def test_news_rules_create_explainable_signal(self):
        signal = classify_article({
            "title": "Oil prices rise amid supply concerns",
            "category": "energy",
        })
        self.assertEqual(signal["action"], "HOLD")
        self.assertEqual(signal["symbols"], [])
        self.assertIn("No exact supported instrument", signal["explanation"])
        self.assertGreater(signal["score"], 0)
        self.assertTrue(signal["matched_keywords"])

        explicit = classify_article({"title": "Nifty rallies on strong growth"})
        self.assertEqual(explicit["action"], "BUY")
        self.assertEqual(explicit["symbols"], ["NIFTYBEES"])
        self.assertEqual(explicit["market_type"], "EQUITY")

    def test_portfolio_trade_uses_virtual_cash_and_tracks_realized_pnl(self):
        account = Portfolio(starting_cash=1_000)
        account.trade("NIFTYBEES", "buy", 2, 10)
        sale = account.trade("NIFTYBEES", "sell", 1, 12)

        self.assertEqual(account.snapshot()["cash"], 992)
        self.assertEqual(account.snapshot()["holdings"][0]["quantity"], 1)
        self.assertEqual(sale["realized_pnl"], 2)
        self.assertEqual(sale["mode"], "simulation")
        self.assertEqual(account.performance()["trade_count"], 2)

    def test_portfolio_rejects_overspending_and_short_selling(self):
        account = Portfolio(starting_cash=100)
        with self.assertRaisesRegex(ValueError, "Insufficient virtual cash"):
            account.trade("NIFTYBEES", "buy", 1, 101)
        with self.assertRaisesRegex(ValueError, "Cannot sell more shares"):
            account.trade("NIFTYBEES", "sell", 1, 10)

    def test_synthetic_backtest_is_repeatable(self):
        self.assertEqual(run_backtest(days=30), run_backtest(days=30))


if __name__ == "__main__":
    unittest.main()
