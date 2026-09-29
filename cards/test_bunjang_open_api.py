import base64
import hashlib
import hmac
import json
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from cards.collectors import (
    AuthenticationError,
    ExternalAPIError,
    InvalidResponseError,
    MarketData,
    RateLimitError,
)
from cards.collectors.markets import BunjangMarketCollector
from cards.models import Card, ListingType, MarketListing, MarketSource
from cards.services.card_matching import is_listing_relevant_to_card
from cards.services.market_search import build_bunjang_search_query


SECRET_BYTES = b'bunjang-test-secret'
BASE64_SECRET = base64.b64encode(SECRET_BYTES).decode()


class FakeResponse:
    def __init__(self, payload=None, status=200, content_type='application/json'):
        self.status_code = status
        self.headers = {'Content-Type': content_type}
        self.body = json.dumps(payload or {'data': []}).encode()

    def iter_content(self, chunk_size):
        yield self.body


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


def decode_segment(segment):
    segment += '=' * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment)


class BunjangAuthenticationTests(TestCase):
    def test_get_jwt_uses_official_hs256_claims(self):
        collector = BunjangMarketCollector('access-key', BASE64_SECRET, now=lambda: 1700000000)
        header_segment, payload_segment, signature_segment = collector.build_jwt('GET').split('.')
        self.assertEqual(json.loads(decode_segment(header_segment)), {'alg': 'HS256', 'typ': 'JWT'})
        payload = json.loads(decode_segment(payload_segment))
        self.assertEqual(payload, {'iat': 1700000000, 'accessKey': 'access-key'})
        expected = hmac.new(
            SECRET_BYTES,
            f'{header_segment}.{payload_segment}'.encode(),
            hashlib.sha256,
        ).digest()
        self.assertEqual(decode_segment(signature_segment), expected)

    def test_nonce_is_only_added_for_mutating_methods(self):
        collector = BunjangMarketCollector('access-key', BASE64_SECRET, now=lambda: 1700000000)
        get_payload = json.loads(decode_segment(collector.build_jwt('GET').split('.')[1]))
        post_payload = json.loads(decode_segment(collector.build_jwt('POST').split('.')[1]))
        self.assertNotIn('nonce', get_payload)
        self.assertIn('nonce', post_payload)

    def test_invalid_base64_secret_is_rejected_without_http(self):
        collector = BunjangMarketCollector('access-key', 'not base64!', session=FakeSession(FakeResponse()))
        with self.assertRaises(AuthenticationError):
            collector.collect('피카츄', 1)
        self.assertEqual(collector.session.calls, [])


class BunjangCollectorTests(TestCase):
    def product(self, **changes):
        item = {
            'pid': 341485879,
            'name': '포켓몬 카드 151 피카츄 025/165',
            'price': 12000,
            'condition': 'LIKE_NEW',
            'saleStatus': 'SELLING',
            'imageUrlTemplate': 'https://media.bunjang.co.kr/product/341485879_{cnt}_1_w640.jpg',
            'imageCount': 2,
            'uid': 999999,
        }
        item.update(changes)
        return item

    def test_product_search_uses_one_official_request_without_pagination(self):
        session = FakeSession(FakeResponse({'data': [self.product()], 'hasNext': True, 'nextCursor': 'ignored'}))
        collector = BunjangMarketCollector('access-key', BASE64_SECRET, session=session)
        result = collector.collect('피카츄 025/165', 1)
        self.assertEqual(len(result), 1)
        self.assertEqual(collector.request_count, 1)
        method, url, options = session.calls[0]
        self.assertEqual((method, url), ('GET', 'https://openapi.bunjang.co.kr/api/v1/products'))
        self.assertEqual(options['params'], {'q': '피카츄 025/165', 'size': 1})
        self.assertNotIn('cursor', options['params'])
        self.assertTrue(options['headers']['Authorization'].startswith('Bearer '))

    def test_normalization_maps_documented_fields_to_current_listing(self):
        data = BunjangMarketCollector.normalize(self.product())
        self.assertEqual(data.external_id, '341485879')
        self.assertEqual(data.title, '포켓몬 카드 151 피카츄 025/165')
        self.assertEqual(data.price, Decimal('12000'))
        self.assertEqual(data.currency, 'KRW')
        self.assertEqual(data.listing_type, ListingType.CURRENT_LISTING)
        self.assertEqual(data.url, 'https://m.bunjang.co.kr/products/341485879')
        self.assertEqual(data.image_url, 'https://media.bunjang.co.kr/product/341485879_1_1_w640.jpg')
        self.assertFalse(hasattr(data, 'uid'))

    def test_non_selling_status_never_becomes_sold(self):
        for status in ('SOLD', 'DELETED', 'RESERVED'):
            with self.subTest(status=status), self.assertRaises(InvalidResponseError):
                BunjangMarketCollector.normalize(self.product(saleStatus=status))

    def test_401_and_429_stop(self):
        for status, error in ((401, AuthenticationError), (429, RateLimitError)):
            collector = BunjangMarketCollector(
                'access-key', BASE64_SECRET, session=FakeSession(FakeResponse(status=status))
            )
            with self.subTest(status=status), self.assertRaises(error):
                collector.collect('피카츄', 1)
            self.assertEqual(collector.request_count, 1)

    def test_result_and_request_hard_limits(self):
        collector = BunjangMarketCollector('access-key', BASE64_SECRET, session=FakeSession(FakeResponse()))
        with self.assertRaises(ValueError):
            collector.collect('피카츄', 6)
        collector.collect('피카츄', 1)
        with self.assertRaises(ExternalAPIError):
            collector.collect('피카츄', 1)
        self.assertEqual(len(collector.session.calls), 1)

    def test_query_prefers_korean_name_and_matching_rejects_wrong_or_bundle(self):
        card = Card.objects.create(
            external_id='query-card', name_ko='피카츄', name_en='Pikachu', set_name='포켓몬 카드 151',
            card_number='025/165', rarity='C', language='KO', source='POKEMON_KOREA',
        )
        self.assertEqual(build_bunjang_search_query(card), '피카츄 025/165 포켓몬 카드 151')
        self.assertTrue(is_listing_relevant_to_card(card, self.product()['name']))
        self.assertFalse(is_listing_relevant_to_card(card, '피카츄 173/165'))
        self.assertFalse(is_listing_relevant_to_card(card, '피카츄 025/165 10장 묶음'))


@override_settings(BUNJANG_ACCESS_KEY='', BUNJANG_SECRET_KEY='')
class BunjangCommandTests(TestCase):
    def make_card(self, source='POKEMON_KOREA'):
        return Card.objects.create(
            external_id=f'command-{Card.objects.count()}', name_ko='피카츄', name_en='Pikachu',
            set_name='포켓몬 카드 151', card_number='025/165', rarity='C', language='KO', source=source,
        )

    @patch('cards.collectors.markets.bunjang.requests.Session.request')
    def test_missing_credentials_skips_without_http(self, request):
        card = self.make_card()
        output = StringIO()
        call_command('update_bunjang', card_id=card.pk, dry_run=True, stdout=output)
        self.assertIn('SKIPPED', output.getvalue())
        request.assert_not_called()

    def test_demo_and_hard_limit_are_rejected(self):
        demo = self.make_card(source='DEMO')
        with self.assertRaises(CommandError):
            call_command('update_bunjang', card_id=demo.pk, dry_run=True)
        with self.assertRaises(CommandError):
            call_command('update_bunjang', card_id=demo.pk, limit=6, dry_run=True)

    @override_settings(BUNJANG_ACCESS_KEY='access-key', BUNJANG_SECRET_KEY=BASE64_SECRET)
    @patch('cards.management.commands.update_bunjang.BunjangMarketCollector')
    def test_dry_run_writes_nothing(self, collector_class):
        card = self.make_card()
        collector = collector_class.return_value
        collector.is_configured = True
        collector.request_count = 1
        collector.collect.return_value = [MarketData(
            external_id='341485879', title='포켓몬 카드 151 피카츄 025/165',
            price=Decimal('12000'), currency='KRW',
            url='https://m.bunjang.co.kr/products/341485879', image_url='',
            listing_type='CURRENT_LISTING', occurred_at=None, collected_at=timezone.now(), source='BUNJANG',
        )]
        call_command('update_bunjang', card_id=card.pk, dry_run=True)
        self.assertEqual(MarketListing.objects.count(), 0)
        self.assertEqual(MarketSource.objects.count(), 0)

    @override_settings(BUNJANG_ACCESS_KEY='access-key', BUNJANG_SECRET_KEY=BASE64_SECRET)
    @patch('cards.management.commands.update_bunjang.BunjangMarketCollector')
    def test_repeated_write_upserts_same_listing(self, collector_class):
        card = self.make_card()
        collector = collector_class.return_value
        collector.is_configured = True
        collector.request_count = 1
        collector.collect.return_value = [MarketData(
            external_id='341485879', title='포켓몬 카드 151 피카츄 025/165',
            price=Decimal('12000'), currency='KRW',
            url='https://m.bunjang.co.kr/products/341485879', image_url='',
            listing_type='CURRENT_LISTING', occurred_at=None, collected_at=timezone.now(), source='BUNJANG',
        )]
        call_command('update_bunjang', card_id=card.pk, write=True)
        call_command('update_bunjang', card_id=card.pk, write=True)
        self.assertEqual(MarketListing.objects.count(), 1)
        self.assertEqual(MarketSource.objects.get().name, '번개장터')
