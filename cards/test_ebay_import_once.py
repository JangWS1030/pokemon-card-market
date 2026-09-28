import os
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from cards.collectors import AuthenticationError, MarketData
from cards.models import Card, Condition, MarketListing, MarketSource, PriceHistory
from cards.services.demo_data import seed_demo_data


IMPORT_ENVIRONMENT = {
    'EBAY_CLIENT_ID': 'mock-client-id',
    'EBAY_CLIENT_SECRET': 'mock-client-secret',
    'EBAY_IMPORT_CARD_SOURCE': 'JUSTTCG',
    'EBAY_IMPORT_CARD_NUMBER': '025/165',
    'EBAY_IMPORT_CARD_SET': 'SV: Scarlet & Violet 151',
    'EBAY_IMPORT_LIMIT': '3',
}


def market_data(external_id, title, price='10.00'):
    return MarketData(
        external_id=external_id,
        title=title,
        price=Decimal(price),
        currency='USD',
        url=f'https://www.ebay.com/itm/{external_id}',
        collected_at=timezone.now(),
        source='EBAY',
    )


class ImportEbayOnceTests(TestCase):
    def setUp(self):
        self.card = Card.objects.create(
            external_id='justtcg-pikachu-025',
            name_ko='',
            name_en='Pikachu',
            set_name='SV: Scarlet & Violet 151',
            card_number='025/165',
            rarity='Common',
            language='UNKNOWN',
            source='JUSTTCG',
        )

    @patch('cards.management.commands.import_ebay_once.EbayMarketCollector')
    def test_missing_import_environment_skips_without_http_or_writes(self, collector_class):
        required_names = (
            'EBAY_IMPORT_CARD_SOURCE',
            'EBAY_IMPORT_CARD_NUMBER',
            'EBAY_IMPORT_CARD_SET',
        )
        for missing_name in required_names:
            with self.subTest(missing_name=missing_name):
                environment = {**IMPORT_ENVIRONMENT}
                environment.pop(missing_name)
                with patch.dict(os.environ, environment, clear=True):
                    call_command('import_ebay_once', stdout=StringIO())

        collector_class.assert_not_called()
        self.assertEqual(MarketListing.objects.count(), 0)
        self.assertEqual(PriceHistory.objects.count(), 0)

    @patch('cards.management.commands.import_ebay_once.EbayMarketCollector')
    def test_missing_or_ambiguous_card_skips_without_http(self, collector_class):
        missing_environment = {
            **IMPORT_ENVIRONMENT,
            'EBAY_IMPORT_CARD_NUMBER': '999/999',
        }
        with patch.dict(os.environ, missing_environment, clear=True):
            call_command('import_ebay_once', stdout=StringIO())

        Card.objects.create(
            external_id='another-pikachu',
            name_ko='',
            name_en='Pikachu',
            set_name=self.card.set_name,
            card_number=self.card.card_number,
            language='UNKNOWN',
            source='JUSTTCG',
        )
        with patch.dict(os.environ, IMPORT_ENVIRONMENT, clear=True):
            call_command('import_ebay_once', stdout=StringIO())

        collector_class.assert_not_called()
        self.assertEqual(MarketListing.objects.count(), 0)

    @patch('cards.management.commands.import_ebay_once.EbayMarketCollector')
    def test_demo_card_and_invalid_limits_skip_without_http(self, collector_class):
        demo_environment = {
            **IMPORT_ENVIRONMENT,
            'EBAY_IMPORT_CARD_SOURCE': 'DEMO',
        }
        with patch.dict(os.environ, demo_environment, clear=True):
            call_command('import_ebay_once', stdout=StringIO())

        for invalid_limit in ('invalid', '0', '4'):
            with self.subTest(limit=invalid_limit):
                environment = {**IMPORT_ENVIRONMENT, 'EBAY_IMPORT_LIMIT': invalid_limit}
                with patch.dict(os.environ, environment, clear=True):
                    call_command('import_ebay_once', stdout=StringIO())

        collector_class.assert_not_called()

    @patch('cards.management.commands.import_ebay_once.EbayMarketCollector')
    def test_default_limit_is_three_and_missing_credentials_make_no_request(
        self,
        collector_class,
    ):
        collector = collector_class.return_value
        collector.is_configured = False
        environment = {**IMPORT_ENVIRONMENT, 'EBAY_IMPORT_LIMIT': ''}

        with patch.dict(os.environ, environment, clear=True):
            call_command('import_ebay_once', stdout=StringIO())

        collector.collect.assert_not_called()
        self.assertEqual(MarketListing.objects.count(), 0)

    @patch('cards.management.commands.import_ebay_once.EbayMarketCollector')
    def test_limits_one_to_three_and_default_are_forwarded(self, collector_class):
        collector = collector_class.return_value
        collector.is_configured = True
        collector.collect.return_value = []

        for configured_limit, expected_limit in (('1', 1), ('2', 2), ('3', 3), ('', 3)):
            with self.subTest(limit=configured_limit or 'default'):
                collector.collect.reset_mock()
                environment = {**IMPORT_ENVIRONMENT, 'EBAY_IMPORT_LIMIT': configured_limit}
                with patch.dict(os.environ, environment, clear=True):
                    call_command('import_ebay_once', stdout=StringIO())
                self.assertEqual(collector.collect.call_args.kwargs['limit'], expected_limit)
                collector.collect.assert_called_once()

    @patch('cards.management.commands.import_ebay_once.EbayMarketCollector')
    def test_import_calls_collector_once_caps_results_and_calculates_histories(
        self,
        collector_class,
    ):
        collector = collector_class.return_value
        collector.is_configured = True
        collector.collect.return_value = [
            market_data('raw-item', 'Pokemon 151 Pikachu 025/165 raw', '12.00'),
            market_data('psa-item', 'Pokemon 151 Pikachu 025/165 PSA 10', '30.00'),
            market_data('unknown-item', 'Pokemon 151 Pikachu 025/165 bundle', '8.00'),
            market_data('ignored-fourth', 'Pokemon 151 Pikachu 025/165 CGC 10', '40.00'),
        ]
        output = StringIO()

        with patch.dict(os.environ, IMPORT_ENVIRONMENT, clear=True):
            call_command('import_ebay_once', stdout=output)

        collector.collect.assert_called_once_with(
            query='Pikachu 025/165 SV: Scarlet & Violet 151 Pokemon',
            limit=3,
        )
        self.assertEqual(MarketListing.objects.count(), 3)
        self.assertEqual(
            set(MarketListing.objects.values_list('condition', flat=True)),
            {Condition.RAW, Condition.PSA, Condition.UNKNOWN},
        )
        self.assertEqual(PriceHistory.objects.count(), 2)
        self.assertIn('Returned: 3', output.getvalue())
        self.assertIn('Unknown condition: 1', output.getvalue())
        self.assertNotIn('mock-client-id', output.getvalue())
        self.assertNotIn('mock-client-secret', output.getvalue())

    @patch('cards.management.commands.import_ebay_once.EbayMarketCollector')
    def test_zero_results_is_a_success_without_db_writes(self, collector_class):
        collector = collector_class.return_value
        collector.is_configured = True
        collector.collect.return_value = []
        output = StringIO()

        with patch.dict(os.environ, IMPORT_ENVIRONMENT, clear=True):
            call_command('import_ebay_once', stdout=output)

        self.assertIn('Returned: 0', output.getvalue())
        self.assertEqual(MarketSource.objects.count(), 0)
        self.assertEqual(MarketListing.objects.count(), 0)
        self.assertEqual(PriceHistory.objects.count(), 0)

    @patch('cards.management.commands.import_ebay_once.EbayMarketCollector')
    def test_repeated_external_id_updates_without_duplicate(self, collector_class):
        collector = collector_class.return_value
        collector.is_configured = True
        collector.collect.side_effect = [
            [market_data('same-item', 'Pokemon Pikachu 025/165 raw', '10.00')],
            [market_data('same-item', 'Pokemon Pikachu 025/165 raw', '14.00')],
        ]

        with patch.dict(os.environ, IMPORT_ENVIRONMENT, clear=True):
            call_command('import_ebay_once', stdout=StringIO())
            call_command('import_ebay_once', stdout=StringIO())

        self.assertEqual(MarketListing.objects.count(), 1)
        self.assertEqual(MarketListing.objects.get().price, Decimal('14.00'))

    @patch('cards.management.commands.import_ebay_once.EbayMarketCollector')
    def test_bgs_and_cgc_listings_create_price_histories(self, collector_class):
        collector = collector_class.return_value
        collector.is_configured = True
        collector.collect.side_effect = [
            [market_data('bgs-item', 'Pokemon Pikachu 025/165 BGS 9.5', '25.00')],
            [market_data('cgc-item', 'Pokemon Pikachu 025/165 CGC 10', '35.00')],
        ]

        with patch.dict(os.environ, IMPORT_ENVIRONMENT, clear=True):
            call_command('import_ebay_once', stdout=StringIO())
            call_command('import_ebay_once', stdout=StringIO())

        self.assertTrue(MarketListing.objects.filter(condition=Condition.BGS).exists())
        self.assertTrue(MarketListing.objects.filter(condition=Condition.CGC).exists())
        self.assertTrue(PriceHistory.objects.filter(condition=Condition.BGS).exists())
        self.assertTrue(PriceHistory.objects.filter(condition=Condition.CGC).exists())

    @patch('cards.management.commands.import_ebay_once.EbayMarketCollector')
    def test_demo_data_is_preserved_even_when_external_id_matches(self, collector_class):
        seed_demo_data()
        demo_source = MarketSource.objects.get(code='DEMO')
        demo_listing_ids = set(
            MarketListing.objects.filter(market_source=demo_source).values_list('pk', flat=True)
        )
        demo_history_ids = set(
            PriceHistory.objects.filter(card__source='DEMO').values_list('pk', flat=True)
        )
        collector = collector_class.return_value
        collector.is_configured = True
        collector.collect.return_value = [
            market_data(
                'demo-listing-001-raw-usd',
                'Pokemon 151 Pikachu 025/165 raw',
            )
        ]

        with patch.dict(os.environ, IMPORT_ENVIRONMENT, clear=True):
            call_command('import_ebay_once', stdout=StringIO())

        self.assertEqual(
            set(
                MarketListing.objects.filter(market_source=demo_source).values_list(
                    'pk', flat=True
                )
            ),
            demo_listing_ids,
        )
        self.assertEqual(
            set(PriceHistory.objects.filter(card__source='DEMO').values_list('pk', flat=True)),
            demo_history_ids,
        )
        self.assertEqual(Card.objects.filter(source='DEMO').count(), 12)
        self.assertEqual(MarketListing.objects.filter(market_source__code='DEMO').count(), 8)
        self.assertEqual(PriceHistory.objects.filter(card__source='DEMO').count(), 24)

    @patch('cards.management.commands.import_ebay_once.EbayMarketCollector')
    def test_api_failure_has_no_partial_writes_or_secret_output(self, collector_class):
        collector = collector_class.return_value
        collector.is_configured = True
        collector.collect.side_effect = AuthenticationError(
            'eBay OAuth failed: status=401, error=invalid_client, description=safe'
        )

        with patch.dict(os.environ, IMPORT_ENVIRONMENT, clear=True):
            with self.assertRaises(CommandError) as raised:
                call_command('import_ebay_once', stdout=StringIO())

        message = str(raised.exception)
        self.assertNotIn(IMPORT_ENVIRONMENT['EBAY_CLIENT_ID'], message)
        self.assertNotIn(IMPORT_ENVIRONMENT['EBAY_CLIENT_SECRET'], message)
        self.assertEqual(MarketSource.objects.count(), 0)
        self.assertEqual(MarketListing.objects.count(), 0)
        self.assertEqual(PriceHistory.objects.count(), 0)
