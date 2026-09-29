from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cards.collectors import (
    AuthenticationError,
    CollectorTimeoutError,
    ExternalAPIError,
    InvalidResponseError,
    MarketData,
    RateLimitError,
    RequestSafetyPolicy,
)
from cards.collectors.card_data import PokemonKoreaCardCollector
from cards.collectors.card_data.pokemon_korea import validate_official_image_url
from cards.collectors.markets import BreakMarketCollector
from cards.collectors.public_http import PublicHttpClient
from cards.models import Card, Condition, ListingType, MarketListing, MarketRegion, MarketSource
from cards.services.card_matching import is_listing_relevant_to_card
from cards.services.condition_classifier import classify_condition
from cards.services.market_importer import save_market_listing
from cards.services.price_calculator import calculate_price_groups


POKEMON_HTML = b'''<!doctype html><html><body>
<span class="card-hp title">\xed\x94\xbc\xec\xb9\xb4\xec\xb8\x84</span>
<span class="p_num">025/165 C</span>
<a href="/cards?s=151">\xec\x8a\xa4\xec\xb9\xbc\xeb\xa0\x9b&amp;\xeb\xb0\x94\xec\x9d\xb4\xec\x98\xac\xeb\xa0\x9b \xea\xb0\x95\xed\x99\x94 \xed\x99\x95\xec\x9e\xa5\xed\x8c\xa9 \xe3\x80\x8c\xed\x8f\xac\xec\xbc\x93\xeb\xaa\xac \xec\xb9\xb4\xeb\x93\x9c 151\xe3\x80\x8d</a>
<img class="feature_image" src="https://cards.image.pokemonkorea.co.kr/data/wmimages/SV/SV2a/SV2a_025.png?w=512">
</body></html>'''

BREAK_HTML = '''<!doctype html><html><head>
<meta property="og:title" content="피카츄 SV2a 025/165 경매 · 판매자별명">
<meta property="og:description" content="[#407195] 피카츄 SV2a 025/165 - 트레이딩 카드. 경매 입찰 상품. 가격 12,000원 (현재 입찰가). 판매자 판매자별명">
<meta property="og:image" content="https://d2ot1525u67uvs.cloudfront.net/uploads/example.jpg">
</head></html>'''.encode()


class FakeResponse:
    def __init__(self, body=b'', status=200, content_type='text/html; charset=utf-8', headers=None):
        self.body = body
        self.status_code = status
        self.headers = {'Content-Type': content_type, **(headers or {})}

    def iter_content(self, chunk_size):
        yield self.body


class FakeSession:
    def __init__(self, *responses, error=None):
        self.responses = list(responses)
        self.error = error
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.error:
            raise self.error
        return self.responses.pop(0)


class PublicHttpSafetyTests(TestCase):
    def make_http_client(self, response, **kwargs):
        return PublicHttpClient(
            {'example.com'},
            policy=RequestSafetyPolicy(request_budget=2),
            session=FakeSession(response),
            **kwargs,
        )

    def test_transparent_get_uses_timeout_stream_and_no_automatic_redirect(self):
        session = FakeSession(FakeResponse(b'<html>ok</html>'))
        client = PublicHttpClient({'example.com'}, session=session)
        self.assertIn('ok', client.get_html('https://example.com/item').text)
        options = session.calls[0][2]
        self.assertEqual(options['timeout'], 10)
        self.assertTrue(options['stream'])
        self.assertFalse(options['allow_redirects'])
        self.assertIn('low-volume', options['headers']['User-Agent'])

    def test_401_403_and_429_stop_immediately(self):
        cases = ((401, AuthenticationError), (403, ExternalAPIError), (429, RateLimitError))
        for status, error in cases:
            with self.subTest(status=status), self.assertRaises(error):
                self.make_http_client(FakeResponse(status=status)).get_html('https://example.com/item')

    def test_challenge_stops(self):
        with self.assertRaises(ExternalAPIError):
            self.make_http_client(FakeResponse(b'<title>Just a moment...</title>captcha')).get_html(
                'https://example.com/item'
            )

    def test_unexpected_content_type_stops(self):
        with self.assertRaises(InvalidResponseError):
            self.make_http_client(
                FakeResponse(b'{}', content_type='application/json')
            ).get_html('https://example.com/item')

    def test_oversized_header_and_stream_stop(self):
        with self.assertRaises(InvalidResponseError):
            self.make_http_client(FakeResponse(headers={'Content-Length': '101'}), max_response_bytes=100).get_html(
                'https://example.com/item'
            )
        with self.assertRaises(InvalidResponseError):
            self.make_http_client(FakeResponse(b'x' * 101), max_response_bytes=100).get_html(
                'https://example.com/item'
            )

    def test_wrong_host_and_cross_host_redirect_are_rejected(self):
        with self.assertRaises(InvalidResponseError):
            self.make_http_client(FakeResponse()).get_html('https://other.example/item')
        session = FakeSession(FakeResponse(status=302, headers={'Location': 'https://evil.example/item'}))
        client = PublicHttpClient({'example.com'}, session=session)
        with self.assertRaises(InvalidResponseError):
            client.get_html('https://example.com/item')
        self.assertEqual(len(session.calls), 1)

    def test_timeout_is_not_retried(self):
        session = FakeSession(error=requests.Timeout())
        client = PublicHttpClient({'example.com'}, session=session)
        with self.assertRaises(CollectorTimeoutError):
            client.get_html('https://example.com/item')
        self.assertEqual(len(session.calls), 1)

    def test_request_budget_stops_second_request(self):
        session = FakeSession(FakeResponse(b'<html>ok</html>'))
        client = PublicHttpClient(
            {'example.com'},
            policy=RequestSafetyPolicy(request_budget=1),
            session=session,
        )
        client.get_html('https://example.com/one')
        with self.assertRaises(ExternalAPIError):
            client.get_html('https://example.com/two')
        self.assertEqual(len(session.calls), 1)


class PokemonKoreaPublicCollectorTests(TestCase):
    def collector(self):
        session = FakeSession(
            FakeResponse(POKEMON_HTML),
            FakeResponse(content_type='image/png'),
        )
        client = PublicHttpClient(
            {'pokemoncard.co.kr', 'cards.image.pokemonkorea.co.kr'},
            policy=PokemonKoreaCardCollector.REQUEST_POLICY,
            session=session,
        )
        return PokemonKoreaCardCollector(client), session

    def make_card(self, source='JUSTTCG'):
        return Card.objects.create(
            external_id='pikachu-025',
            name_ko='',
            name_en='Pikachu',
            set_name='SV: Scarlet & Violet 151',
            card_number='025/165',
            rarity='Common',
            language='UNKNOWN',
            source=source,
        )

    def test_preserved_parser_normalizes_only_discovered_official_image(self):
        data = PokemonKoreaCardCollector.parse_detail_html(
            'https://pokemoncard.co.kr/cards/detail/BS2023014025',
            POKEMON_HTML.decode(),
        )
        self.assertEqual(data.name_ko, '피카츄')
        self.assertEqual(data.card_number, '025/165')
        self.assertEqual(data.rarity, 'C')
        self.assertEqual(data.external_id, 'BS2023014025')
        self.assertTrue(data.image_url.startswith('https://cards.image.pokemonkorea.co.kr/'))

    def test_automatic_collector_is_disabled_before_http(self):
        collector, session = self.collector()
        with self.assertRaises(ExternalAPIError):
            collector.collect_url('https://pokemoncard.co.kr/cards/detail/BS2023014025')
        self.assertFalse(collector.HTTP_ENABLED)
        self.assertEqual(session.calls, [])

    def test_guessed_or_non_detail_url_is_not_requested(self):
        collector, session = self.collector()
        with self.assertRaises(ExternalAPIError):
            collector.collect_url('https://pokemoncard.co.kr/cards/025-165')
        self.assertEqual(session.calls, [])

    def test_hard_max_three_cards(self):
        collector, _ = self.collector()
        with self.assertRaises(InvalidResponseError):
            collector.collect_urls(['https://pokemoncard.co.kr/cards/detail/x'] * 4)

    def test_valid_official_image_url(self):
        url = 'https://cards.image.pokemonkorea.co.kr/data/card.png?w=512'
        self.assertEqual(validate_official_image_url(url), url)

    def test_wrong_image_hostname_is_rejected(self):
        with self.assertRaises(InvalidResponseError):
            validate_official_image_url('https://example.com/card.png')

    def test_http_image_url_is_rejected(self):
        with self.assertRaises(InvalidResponseError):
            validate_official_image_url('http://cards.image.pokemonkorea.co.kr/card.png')

    def test_hostname_suffix_trick_is_rejected(self):
        with self.assertRaises(InvalidResponseError):
            validate_official_image_url(
                'https://cards.image.pokemonkorea.co.kr.evil.com/card.png'
            )

    def test_credentials_in_image_url_are_rejected(self):
        with self.assertRaises(InvalidResponseError):
            validate_official_image_url(
                'https://user:password@cards.image.pokemonkorea.co.kr/card.png'
            )

    def test_private_ip_and_oversized_image_urls_are_rejected(self):
        for url in (
            'https://127.0.0.1/card.png',
            'https://cards.image.pokemonkorea.co.kr/' + ('a' * 2050),
        ):
            with self.subTest(url=url), self.assertRaises(InvalidResponseError):
                validate_official_image_url(url)

    def test_manual_command_dry_run_does_not_write(self):
        card = self.make_card()
        output = StringIO()
        call_command(
            'set_card_image', card_id=card.pk,
            url='https://cards.image.pokemonkorea.co.kr/card.png',
            dry_run=True, stdout=output,
        )
        card.refresh_from_db()
        self.assertFalse(card.image_url)
        self.assertIn('Mode: dry-run', output.getvalue())
        self.assertIn('DB writes: 0', output.getvalue())

    @patch('cards.management.commands.set_card_image.PublicHttpClient')
    def test_optional_image_check_uses_one_head_request(self, client_class):
        card = self.make_card()
        client_class.return_value.request_count = 1
        output = StringIO()
        url = 'https://cards.image.pokemonkorea.co.kr/card.png'
        call_command(
            'set_card_image', card_id=card.pk, url=url,
            check_image=True, dry_run=True, stdout=output,
        )
        client_class.return_value.head_image.assert_called_once_with(url)
        self.assertIn('Image check requests: 1', output.getvalue())
        card.refresh_from_db()
        self.assertFalse(card.image_url)

    def test_manual_command_write_updates_only_image_and_rejects_demo(self):
        card = self.make_card()
        original = {
            field.attname: getattr(card, field.attname)
            for field in Card._meta.concrete_fields
            if field.name != 'image_url'
        }
        call_command(
            'set_card_image', card_id=card.pk,
            url='https://cards.image.pokemonkorea.co.kr/card.png', write=True,
        )
        card.refresh_from_db()
        self.assertEqual(card.image_url, 'https://cards.image.pokemonkorea.co.kr/card.png')
        unchanged = {
            field.attname: getattr(card, field.attname)
            for field in Card._meta.concrete_fields
            if field.name != 'image_url'
        }
        self.assertEqual(unchanged, original)
        demo = self.make_card(source='DEMO')
        with self.assertRaises(CommandError):
            call_command(
                'set_card_image', card_id=demo.pk,
                url='https://cards.image.pokemonkorea.co.kr/card.png', write=True,
            )

    @patch('cards.management.commands.set_card_image.PublicHttpClient')
    def test_failed_image_check_prevents_write(self, client_class):
        card = self.make_card()
        client_class.return_value.head_image.side_effect = ExternalAPIError('HTTP 410')
        with self.assertRaises(CommandError):
            call_command(
                'set_card_image', card_id=card.pk,
                url='https://cards.image.pokemonkorea.co.kr/card.png',
                check_image=True, write=True,
            )
        card.refresh_from_db()
        self.assertFalse(card.image_url)

    def test_legacy_collection_command_reports_disabled_without_http(self):
        output = StringIO()
        call_command('collect_pokemon_korea_image', dry_run=True, stdout=output)
        self.assertIn('HTTP 410', output.getvalue())
        self.assertIn('Automatic collection is disabled', output.getvalue())


class BreakPublicCollectorTests(TestCase):
    def collector(self):
        session = FakeSession(FakeResponse(BREAK_HTML))
        client = PublicHttpClient({'app.break.market'}, session=session)
        return BreakMarketCollector(client), session

    def fixture(self, **changes):
        item = {
            'external_id': '407195', 'title': '피카츄 025/165', 'price': '12,000원',
            'url': 'https://app.break.market/products/407195/example',
            'image_url': 'https://d2ot1525u67uvs.cloudfront.net/uploads/example.jpg',
            'collected_at': timezone.now(), 'data_type': 'CURRENT_LISTING',
        }
        item.update(changes)
        return item

    def make_card(self):
        return Card.objects.create(
            external_id='ko-025', name_ko='피카츄', name_en='Pikachu', set_name='SV2a 151',
            card_number='025/165', rarity='C', language='KO', source='POKEMON_KOREA',
        )

    def test_public_current_auction_normalization_and_seller_ignored(self):
        collector, _ = self.collector()
        data = collector.collect_url('https://app.break.market/products/407195/example')
        self.assertEqual(data.external_id, '407195')
        self.assertEqual(data.price, Decimal('12000'))
        self.assertEqual(data.listing_type, ListingType.CURRENT_LISTING)
        self.assertIn('진행 중 경매', data.title)
        self.assertNotIn('판매자별명', data.title)
        self.assertTrue(data.image_url.startswith('https://d2ot1525u67uvs.cloudfront.net/'))

    def test_confirmed_auction_result_is_not_sold(self):
        data = BreakMarketCollector.normalize(self.fixture(
            data_type='AUCTION_RESULT', final_result_confirmed=True,
            occurred_at=timezone.now() - timedelta(days=1),
        ))
        self.assertEqual(data.listing_type, ListingType.AUCTION_RESULT)
        self.assertNotEqual(data.listing_type, ListingType.SOLD)

    def test_unconfirmed_auction_result_is_rejected(self):
        with self.assertRaises(InvalidResponseError):
            BreakMarketCollector.normalize(self.fixture(data_type='AUCTION_RESULT'))

    def test_card_number_mismatch_and_bundle_are_rejected(self):
        card = self.make_card()
        self.assertFalse(is_listing_relevant_to_card(card, '피카츄 173/165'))
        self.assertFalse(is_listing_relevant_to_card(card, '피카츄 025/165 10장 묶음'))

    def test_collector_has_single_request_budget(self):
        collector, _ = self.collector()
        self.assertEqual(collector.REQUEST_POLICY.request_budget, 1)
        self.assertEqual(collector.REQUEST_POLICY.retry_limit, 0)
        self.assertEqual(collector.REQUEST_POLICY.timeout_seconds, 10)

    @patch('cards.management.commands.collect_break_once.BreakMarketCollector')
    def test_command_dry_run_has_no_database_write(self, collector_class):
        card = self.make_card()
        collector = collector_class.return_value
        collector.collect_url.return_value = MarketData(
            external_id='407195', title='진행 중 경매 · 피카츄 025/165',
            price=Decimal('12000'), currency='KRW',
            url='https://app.break.market/products/407195/example',
            image_url='', listing_type='CURRENT_LISTING', occurred_at=None,
            collected_at=timezone.now(), source='BREAK',
        )
        collector.request_count = 1
        output = StringIO()
        call_command('collect_break_once', card_id=card.pk, url='https://app.break.market/products/407195/example', dry_run=True, stdout=output)
        self.assertEqual(MarketListing.objects.count(), 0)
        self.assertFalse(MarketSource.objects.filter(code='BREAK').exists())
        self.assertIn('Mode: dry-run', output.getvalue())


class DomesticTypeAndUiTests(TestCase):
    def setUp(self):
        self.card = Card.objects.create(
            external_id='ui-card', name_ko='피카츄', name_en='Pikachu', set_name='151',
            card_number='025/165', rarity='C', language='KO', source='POKEMON_KOREA',
            image_url='https://cards.image.pokemonkorea.co.kr/card.png',
        )
        self.break_source = MarketSource.objects.create(
            code='BREAK', name='BREAK', base_url='https://app.break.market', market_region=MarketRegion.KR,
        )

    def save(self, external_id, listing_type):
        data = MarketData(
            external_id=external_id, title='피카츄 025/165', price=Decimal('12000'),
            currency='KRW', url=f'https://app.break.market/products/{external_id}/example',
            image_url='', listing_type=listing_type,
            occurred_at=timezone.now() if listing_type == ListingType.AUCTION_RESULT else None,
            collected_at=timezone.now(), source='BREAK',
        )
        return save_market_listing(data, self.card, self.break_source, classify_condition(data.title, card_matched=True)).listing

    def test_break_current_and_auction_price_groups_are_separate(self):
        self.save('one', ListingType.CURRENT_LISTING)
        self.save('two', ListingType.AUCTION_RESULT)
        groups = calculate_price_groups(MarketListing.objects.all())
        self.assertEqual({group.listing_type for group in groups}, {'CURRENT_LISTING', 'AUCTION_RESULT'})

    def test_ui_shows_official_image_break_source_and_auction_wording_without_pii(self):
        self.save('one', ListingType.AUCTION_RESULT)
        response = self.client.get(reverse('card-detail', args=[self.card.pk]))
        self.assertContains(response, self.card.image_url)
        self.assertContains(response, 'BREAK')
        self.assertContains(response, '경매 결과')
        self.assertNotContains(response, '실거래 완료')
        self.assertNotContains(response, '판매자별명')
