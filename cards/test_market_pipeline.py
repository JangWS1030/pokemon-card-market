from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from cards.collectors import (
    AuthenticationError,
    CollectorTimeoutError,
    InvalidResponseError,
    MarketData,
    MissingFieldError,
    RateLimitError,
)
from cards.collectors.markets import EbayMarketCollector
from cards.models import Card, Condition, MarketListing, MarketRegion, MarketSource, PriceHistory
from cards.services.card_matching import match_card
from cards.services.condition_classifier import classify_condition
from cards.services.market_importer import save_market_listing
from cards.services.price_calculator import calculate_price_groups, remove_iqr_outliers
from cards.services.price_history import save_price_histories


class FakeResponse:
    def __init__(self, status_code=200, payload=None, json_error=None):
        self.status_code = status_code
        self.payload = payload
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


class EbayMarketCollectorTests(TestCase):
    def make_session(self, item_payload=None):
        session = Mock()
        session.post.return_value = FakeResponse(
            payload={'access_token': 'mock-token', 'expires_in': 7200}
        )
        session.get.return_value = FakeResponse(
            payload={
                'itemSummaries': item_payload
                or [
                    {
                        'itemId': 'v1|123|0',
                        'title': 'Pokemon Charizard ex 201/165 PSA 10',
                        'price': {'value': '149.99', 'currency': 'USD'},
                        'itemWebUrl': 'https://www.ebay.com/itm/123',
                    }
                ]
            }
        )
        return session

    def test_collect_uses_oauth_and_normalizes_browse_result(self):
        session = self.make_session()
        collector = EbayMarketCollector('client-id', 'client-secret', session=session)

        results = collector.collect('Charizard 201/165', limit=3)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].external_id, 'v1|123|0')
        self.assertEqual(results[0].price, Decimal('149.99'))
        self.assertEqual(results[0].currency, 'USD')
        self.assertEqual(results[0].source, 'EBAY')
        session.post.assert_called_once()
        self.assertEqual(session.post.call_args.kwargs['auth'], ('client-id', 'client-secret'))
        self.assertEqual(session.get.call_args.kwargs['params']['q'], 'Charizard 201/165')
        self.assertEqual(
            session.get.call_args.kwargs['headers']['X-EBAY-C-MARKETPLACE-ID'],
            'EBAY_US',
        )

    def test_authentication_failure_is_distinguished(self):
        session = Mock()
        session.post.return_value = FakeResponse(status_code=401, payload={})

        with self.assertRaises(AuthenticationError):
            EbayMarketCollector('bad', 'credentials', session=session).collect('Pikachu')

    def test_timeout_is_distinguished(self):
        session = Mock()
        session.post.side_effect = requests.Timeout()

        with self.assertRaises(CollectorTimeoutError):
            EbayMarketCollector('id', 'secret', session=session).collect('Pikachu')

    def test_rate_limit_is_distinguished(self):
        session = Mock()
        session.post.return_value = FakeResponse(
            payload={'access_token': 'mock-token', 'expires_in': 7200}
        )
        session.get.return_value = FakeResponse(status_code=429, payload={})

        with self.assertRaises(RateLimitError):
            EbayMarketCollector('id', 'secret', session=session).collect('Pikachu')

    def test_invalid_json_is_rejected(self):
        session = Mock()
        session.post.return_value = FakeResponse(json_error=ValueError('invalid'))

        with self.assertRaises(InvalidResponseError):
            EbayMarketCollector('id', 'secret', session=session).collect('Pikachu')

    def test_missing_required_item_field_is_rejected(self):
        session = self.make_session([{'itemId': '123', 'title': 'Pikachu'}])

        with self.assertRaises(MissingFieldError):
            EbayMarketCollector('id', 'secret', session=session).collect('Pikachu')


class MatchingAndConditionTests(TestCase):
    def setUp(self):
        self.charizard = Card.objects.create(
            external_id='charizard',
            name_ko='리자몽 ex',
            name_en='Charizard ex',
            set_name='Pokemon 151',
            card_number='201/165',
            rarity='SAR',
            language='EN',
            source='TEST',
        )

    def test_exact_card_number_and_name_match(self):
        matched = match_card(
            'Pokemon 151 Charizard EX 201 / 165 SAR',
            Card.objects.all(),
        )
        self.assertEqual(matched, self.charizard)

    def test_card_name_matches_without_card_number(self):
        matched = match_card('Pokemon Charizard EX single card', Card.objects.all())
        self.assertEqual(matched, self.charizard)

    def test_ambiguous_candidates_are_not_guessed(self):
        Card.objects.create(
            external_id='charizard-2',
            name_ko='리자몽 ex',
            name_en='Charizard ex',
            set_name='Pokemon 151',
            card_number='201/165',
            rarity='SAR',
            language='JP',
            source='TEST',
        )
        self.assertIsNone(match_card('Charizard ex 201/165', Card.objects.all()))

    def test_explicit_language_can_resolve_multiple_candidates(self):
        japanese = Card.objects.create(
            external_id='charizard-jp',
            name_ko='리자몽 ex',
            name_en='Charizard ex',
            set_name='Pokemon 151',
            card_number='201/165',
            rarity='SAR',
            language='JP',
            source='TEST',
        )
        matched = match_card(
            'Japanese Pokemon 151 Charizard ex 201/165 SAR',
            Card.objects.all(),
        )
        self.assertEqual(matched, japanese)

    def test_unmatched_title_returns_none(self):
        self.assertIsNone(match_card('Pokemon Squirtle 007/165', Card.objects.all()))

    def test_condition_variants(self):
        cases = (
            ('Charizard raw card', True, Condition.RAW, None, None),
            ('Charizard PSA10', True, Condition.PSA, 'PSA', Decimal('10')),
            ('Charizard BGS 9.5', True, Condition.BGS, 'BGS', Decimal('9.5')),
            ('Charizard CGC 10', True, Condition.CGC, 'CGC', Decimal('10')),
            ('Charizard sealed booster box', False, Condition.SEALED, None, None),
            ('Charizard PSA slab', True, Condition.UNKNOWN, None, None),
            ('Charizard lot 3 cards', True, Condition.UNKNOWN, None, None),
            ('Unclear collectible', False, Condition.UNKNOWN, None, None),
        )
        for title, matched, condition, company, score in cases:
            with self.subTest(title=title):
                result = classify_condition(title, card_matched=matched)
                self.assertEqual(result.condition, condition)
                self.assertEqual(result.grading_company, company)
                self.assertEqual(result.grading_score, score)


class PricePipelineTests(TestCase):
    def setUp(self):
        self.card = Card.objects.create(
            external_id='price-card',
            name_ko='피카츄',
            name_en='Pikachu',
            set_name='Test Set',
            card_number='025/100',
            language='EN',
            source='TEST',
        )
        self.source = MarketSource.objects.create(
            code='EBAY',
            name='eBay',
            base_url='https://www.ebay.com',
            market_region=MarketRegion.GLOBAL,
        )

    def listing(self, price, condition=Condition.RAW, score=None, currency='USD'):
        return SimpleNamespace(
            card_id=self.card.pk,
            condition=condition,
            grading_score=score,
            currency=currency,
            price=Decimal(str(price)),
            is_active=True,
        )

    def test_iqr_removes_large_outlier(self):
        result = remove_iqr_outliers([10, 11, 12, 13, 100])
        self.assertEqual(result.prices, tuple(map(Decimal, ('10', '11', '12', '13'))))
        self.assertEqual(result.removed_count, 1)
        self.assertFalse(result.used_fallback)

    def test_iqr_is_not_applied_to_small_samples(self):
        result = remove_iqr_outliers([1, 2, 100, 200])
        self.assertEqual(len(result.prices), 4)
        self.assertEqual(result.removed_count, 0)

    @patch(
        'cards.services.price_calculator.quantiles',
        return_value=(Decimal('100'), Decimal('100'), Decimal('100')),
    )
    def test_iqr_falls_back_when_too_few_values_remain(self, _quantiles):
        result = remove_iqr_outliers([1, 2, 3, 4, 5])
        self.assertTrue(result.used_fallback)
        self.assertEqual(result.prices, tuple(map(Decimal, ('1', '2', '3', '4', '5'))))

    def test_calculation_separates_condition_grade_and_currency(self):
        listings = [
            self.listing(10, Condition.RAW, currency='USD'),
            self.listing(12, Condition.RAW, currency='USD'),
            self.listing(100, Condition.PSA, Decimal('9'), 'USD'),
            self.listing(200, Condition.PSA, Decimal('10'), 'USD'),
            self.listing(200000, Condition.PSA, Decimal('10'), 'KRW'),
            self.listing(1, Condition.UNKNOWN, currency='USD'),
        ]

        calculations = calculate_price_groups(listings)

        self.assertEqual(len(calculations), 4)
        raw_usd = next(item for item in calculations if item.condition == Condition.RAW)
        self.assertEqual(raw_usd.median_price, Decimal('11.00'))
        self.assertEqual(raw_usd.average_price, Decimal('11.00'))

    def test_listing_is_updated_by_source_and_external_id(self):
        collected_at = timezone.now()
        first = MarketData(
            external_id='listing-1',
            title='Pikachu 025/100 raw',
            price=Decimal('10.50'),
            currency='USD',
            url='https://www.ebay.com/itm/1',
            collected_at=collected_at,
            source='EBAY',
        )
        condition = classify_condition(first.title, card_matched=True)
        created = save_market_listing(first, self.card, self.source, condition)
        updated_data = MarketData(
            external_id='listing-1',
            title=first.title,
            price=Decimal('12.75'),
            currency='USD',
            url=first.url,
            collected_at=collected_at,
            source='EBAY',
        )
        updated = save_market_listing(updated_data, self.card, self.source, condition)

        self.assertTrue(created.created)
        self.assertFalse(updated.created)
        self.assertEqual(MarketListing.objects.count(), 1)
        self.assertEqual(MarketListing.objects.get().price, Decimal('12.75'))

    def test_price_history_keeps_currency(self):
        calculations = calculate_price_groups([self.listing(19.99)])
        saved = save_price_histories(calculations)

        self.assertEqual(len(saved), 1)
        self.assertEqual(PriceHistory.objects.get().currency, 'USD')


class UpdatePricesCommandTests(TestCase):
    def setUp(self):
        self.card = Card.objects.create(
            external_id='command-card',
            name_ko='피카츄',
            name_en='Pikachu',
            set_name='Test Set',
            card_number='025/100',
            language='EN',
            source='TEST',
        )

    @patch.dict('os.environ', {}, clear=True)
    def test_missing_credentials_exits_without_writes(self):
        output = StringIO()

        call_command('update_prices', stdout=output)

        self.assertIn('EBAY_CLIENT_ID', output.getvalue())
        self.assertEqual(MarketSource.objects.count(), 0)
        self.assertEqual(MarketListing.objects.count(), 0)
        self.assertEqual(PriceHistory.objects.count(), 0)

    @patch.dict(
        'os.environ',
        {'EBAY_CLIENT_ID': 'mock-id', 'EBAY_CLIENT_SECRET': 'mock-secret'},
        clear=True,
    )
    @patch('cards.management.commands.update_prices.EbayMarketCollector.collect')
    def test_dry_run_calls_collector_but_does_not_write(self, collect):
        collect.return_value = [
            MarketData(
                external_id='mock-listing',
                title='Pokemon Pikachu Test Set 025/100 raw',
                price=Decimal('25.00'),
                currency='USD',
                url='https://www.ebay.com/itm/mock',
                collected_at=timezone.now(),
                source='EBAY',
            )
        ]
        output = StringIO()

        call_command(
            'update_prices',
            card_id=self.card.pk,
            limit=1,
            dry_run=True,
            stdout=output,
        )

        self.assertIn('DRY RUN', output.getvalue())
        self.assertEqual(MarketSource.objects.count(), 0)
        self.assertEqual(MarketListing.objects.count(), 0)
        self.assertEqual(PriceHistory.objects.count(), 0)
