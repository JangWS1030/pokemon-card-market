import os
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from cards.collectors import CardData
from cards.collectors.markets import EbayMarketCollector
from cards.models import Card, MarketListing, PriceHistory
from cards.services.demo_data import seed_demo_data


JUSTTCG_FILTERS = {
    'JUSTTCG_API_KEY': 'mock-justtcg-key',
    'JUSTTCG_IMPORT_SET': 'mock-pokemon-set-id',
    'JUSTTCG_IMPORT_NUMBER': '025/100',
}

EBAY_ENVIRONMENT = {
    'EBAY_CLIENT_ID': 'mock-production-client-id',
    'EBAY_CLIENT_SECRET': 'mock-production-client-secret',
    'EBAY_TEST_QUERY': 'Pokemon card test query',
}


def card_data():
    return CardData(
        external_id='mock-justtcg-card-uuid',
        name_ko='',
        name_en='Pikachu',
        set_name='Mock Pokemon Set',
        card_number='025/100',
        rarity='Common',
        language='UNKNOWN',
        image_url=None,
        source='JUSTTCG',
    )


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class ImportJustTCGOnceTests(TestCase):
    @patch('cards.management.commands.import_justtcg_once.JustTCGCardCollector')
    def test_missing_set_or_number_skips_without_collecting(self, collector_class):
        incomplete_environments = (
            {
                'JUSTTCG_API_KEY': 'mock-key',
                'JUSTTCG_IMPORT_NUMBER': '025/100',
            },
            {
                'JUSTTCG_API_KEY': 'mock-key',
                'JUSTTCG_IMPORT_SET': 'mock-set',
            },
        )

        for environment in incomplete_environments:
            with self.subTest(environment=tuple(environment)):
                with patch.dict(os.environ, environment, clear=True):
                    call_command('import_justtcg_once', stdout=StringIO())

        collector_class.assert_not_called()
        self.assertEqual(Card.objects.count(), 0)

    @patch('cards.management.commands.import_justtcg_once.JustTCGCardCollector')
    def test_default_limit_is_five_and_collector_runs_once(self, collector_class):
        collector = collector_class.return_value
        collector.collect.return_value = []
        collector.last_report = SimpleNamespace(returned_cards=0)

        environment = {**JUSTTCG_FILTERS, 'JUSTTCG_IMPORT_LIMIT': ''}
        with patch.dict(os.environ, environment, clear=True):
            call_command('import_justtcg_once', stdout=StringIO())

        collector.collect.assert_called_once_with(
            limit=5,
            set_id=JUSTTCG_FILTERS['JUSTTCG_IMPORT_SET'],
            number=JUSTTCG_FILTERS['JUSTTCG_IMPORT_NUMBER'],
        )
        self.assertEqual(Card.objects.count(), 0)

    @patch('cards.management.commands.import_justtcg_once.JustTCGCardCollector')
    def test_limit_ten_is_allowed(self, collector_class):
        collector = collector_class.return_value
        collector.collect.return_value = []
        collector.last_report = SimpleNamespace(returned_cards=0)
        environment = {**JUSTTCG_FILTERS, 'JUSTTCG_IMPORT_LIMIT': '10'}

        with patch.dict(os.environ, environment, clear=True):
            call_command('import_justtcg_once', stdout=StringIO())

        self.assertEqual(collector.collect.call_args.kwargs['limit'], 10)

    @patch('cards.management.commands.import_justtcg_once.JustTCGCardCollector')
    def test_invalid_limits_skip_without_collecting(self, collector_class):
        for value in ('not-a-number', '0', '11'):
            with self.subTest(value=value):
                environment = {**JUSTTCG_FILTERS, 'JUSTTCG_IMPORT_LIMIT': value}
                with patch.dict(os.environ, environment, clear=True):
                    call_command('import_justtcg_once', stdout=StringIO())

        collector_class.assert_not_called()

    @patch('cards.management.commands.import_justtcg_once.JustTCGCardCollector')
    def test_empty_result_creates_nothing(self, collector_class):
        collector = collector_class.return_value
        collector.collect.return_value = []
        collector.last_report = SimpleNamespace(returned_cards=1)

        with patch.dict(os.environ, JUSTTCG_FILTERS, clear=True):
            call_command('import_justtcg_once', stdout=StringIO())

        self.assertEqual(Card.objects.count(), 0)

    @patch('cards.management.commands.import_justtcg_once.JustTCGCardCollector')
    def test_repeated_import_is_idempotent_and_preserves_demo_data(self, collector_class):
        seed_demo_data()
        demo_card_ids = set(Card.objects.filter(source='DEMO').values_list('pk', flat=True))
        collector = collector_class.return_value
        collector.collect.return_value = [card_data()]
        collector.last_report = SimpleNamespace(returned_cards=1)

        with patch.dict(os.environ, JUSTTCG_FILTERS, clear=True):
            call_command('import_justtcg_once', stdout=StringIO())
            call_command('import_justtcg_once', stdout=StringIO())

        self.assertEqual(Card.objects.filter(source='JUSTTCG').count(), 1)
        self.assertEqual(
            set(Card.objects.filter(source='DEMO').values_list('pk', flat=True)),
            demo_card_ids,
        )
        self.assertEqual(Card.objects.filter(source='DEMO').count(), 12)


class CheckEbayConnectionTests(TestCase):
    def make_session(self, item_summaries=None):
        session = Mock()
        session.post.return_value = FakeResponse(
            payload={'access_token': 'mock-access-token', 'expires_in': 7200}
        )
        session.get.return_value = FakeResponse(
            payload={'itemSummaries': item_summaries if item_summaries is not None else []}
        )
        return session

    def test_collector_uses_production_endpoints(self):
        self.assertEqual(
            EbayMarketCollector.TOKEN_URL,
            'https://api.ebay.com/identity/v1/oauth2/token',
        )
        self.assertEqual(
            EbayMarketCollector.SEARCH_URL,
            'https://api.ebay.com/buy/browse/v1/item_summary/search',
        )
        self.assertEqual(EbayMarketCollector.MARKETPLACE_ID, 'EBAY_US')

    @patch('cards.collectors.markets.ebay.requests.Session')
    def test_missing_credentials_makes_no_http_requests(self, session_class):
        session = session_class.return_value
        environment = {'EBAY_TEST_QUERY': EBAY_ENVIRONMENT['EBAY_TEST_QUERY']}

        with patch.dict(os.environ, environment, clear=True):
            call_command('check_ebay_connection', stdout=StringIO())

        session.post.assert_not_called()
        session.get.assert_not_called()

    @patch('cards.collectors.markets.ebay.requests.Session')
    def test_missing_query_makes_no_http_requests(self, session_class):
        session = session_class.return_value
        environment = {
            'EBAY_CLIENT_ID': EBAY_ENVIRONMENT['EBAY_CLIENT_ID'],
            'EBAY_CLIENT_SECRET': EBAY_ENVIRONMENT['EBAY_CLIENT_SECRET'],
        }

        with patch.dict(os.environ, environment, clear=True):
            call_command('check_ebay_connection', stdout=StringIO())

        session.post.assert_not_called()
        session.get.assert_not_called()

    @patch('cards.collectors.markets.ebay.requests.Session')
    def test_success_uses_one_oauth_and_one_browse_request_without_db_writes(
        self,
        session_class,
    ):
        session = self.make_session(
            [
                {
                    'itemId': 'mock-item-id',
                    'title': 'Pokemon card test listing',
                    'price': {'value': '9.99', 'currency': 'USD'},
                    'itemWebUrl': 'https://www.ebay.com/itm/mock-item',
                }
            ]
        )
        session_class.return_value = session
        output = StringIO()

        with patch.dict(os.environ, EBAY_ENVIRONMENT, clear=True):
            call_command('check_ebay_connection', stdout=output)

        session.post.assert_called_once()
        session.get.assert_called_once()
        self.assertEqual(session.get.call_args.kwargs['params']['limit'], 3)
        self.assertNotIn('offset', session.get.call_args.kwargs['params'])
        self.assertIn('Marketplace: EBAY_US', output.getvalue())
        self.assertIn('Results: 1', output.getvalue())
        for sensitive_value in (
            EBAY_ENVIRONMENT['EBAY_CLIENT_ID'],
            EBAY_ENVIRONMENT['EBAY_CLIENT_SECRET'],
            'mock-access-token',
        ):
            self.assertNotIn(sensitive_value, output.getvalue())
        self.assertEqual(Card.objects.count(), 0)
        self.assertEqual(MarketListing.objects.count(), 0)
        self.assertEqual(PriceHistory.objects.count(), 0)

    @patch('cards.collectors.markets.ebay.requests.Session')
    def test_oauth_failure_does_not_call_browse(self, session_class):
        session = session_class.return_value
        session.post.return_value = FakeResponse(status_code=401, payload={})

        with patch.dict(os.environ, EBAY_ENVIRONMENT, clear=True):
            with self.assertRaises(CommandError):
                call_command('check_ebay_connection', stdout=StringIO())

        session.post.assert_called_once()
        session.get.assert_not_called()

    @patch('cards.collectors.markets.ebay.requests.Session')
    def test_zero_results_does_not_retry_or_paginate(self, session_class):
        session = self.make_session(item_summaries=[])
        session_class.return_value = session
        output = StringIO()

        with patch.dict(os.environ, EBAY_ENVIRONMENT, clear=True):
            call_command('check_ebay_connection', stdout=output)

        session.post.assert_called_once()
        session.get.assert_called_once()
        self.assertIn('Results: 0', output.getvalue())
