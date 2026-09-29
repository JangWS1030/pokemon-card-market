from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from cards.collectors import ExternalAPIError, InvalidResponseError
from cards.collectors.card_data import PokemonKoreaCardCollector
from cards.collectors.markets import (
    BunjangMarketCollector,
    KreamMarketCollector,
    NaverCafeCardmvkCollector,
)
from cards.models import Card, Condition, ListingType
from cards.services.card_importer import import_cards
from cards.services.card_matching import is_listing_relevant_to_card, match_card
from cards.services.condition_classifier import classify_condition
from cards.services.normalization import parse_krw_price


class KoreanPriceParserTests(TestCase):
    def test_explicit_krw_formats_are_normalized(self):
        for value in ('₩12,000', '12,000원', '12000', 'KRW 12000', 12000):
            with self.subTest(value=value):
                self.assertEqual(parse_krw_price(value), Decimal('12000'))

    def test_community_shorthand_is_not_guessed(self):
        for value in ('1.2', '1.5', 1.2, '1만 2천원', '가격문의'):
            with self.subTest(value=value), self.assertRaises(InvalidResponseError):
                parse_krw_price(value)

    def test_zero_negative_and_boolean_are_rejected(self):
        for value in (0, -1000, True, False):
            with self.subTest(value=value), self.assertRaises(InvalidResponseError):
                parse_krw_price(value)


class PokemonKoreaReadinessTests(TestCase):
    def fixture(self, **changes):
        item = {
            'external_id': 'official-025',
            'name_ko': '피카츄',
            'set_name': '강화 확장팩 포켓몬 카드 151',
            'card_number': '025/165',
            'rarity': 'C',
            'image_url': 'https://cards.image.pokemonkorea.co.kr/card/official.png',
        }
        item.update(changes)
        return item

    def test_metadata_preserves_official_korean_values(self):
        data = PokemonKoreaCardCollector.normalize(self.fixture())

        self.assertEqual(data.name_ko, '피카츄')
        self.assertEqual(data.card_number, '025/165')
        self.assertEqual(data.set_name, '강화 확장팩 포켓몬 카드 151')
        self.assertEqual(data.language, 'KO')
        self.assertEqual(data.source, 'POKEMON_KOREA')

    def test_only_known_official_https_image_host_is_kept(self):
        allowed = PokemonKoreaCardCollector.normalize(self.fixture())
        self.assertTrue(allowed.image_url.startswith('https://cards.image.pokemonkorea.co.kr/'))

        for image_url in (
            'http://cards.image.pokemonkorea.co.kr/card/guessed.png',
            'https://example.com/card/025-165.png',
            'https://userinfo@cards.image.pokemonkorea.co.kr/card/a.png',
            '/images/guessed.png',
        ):
            with self.subTest(image_url=image_url):
                data = PokemonKoreaCardCollector.normalize(
                    self.fixture(image_url=image_url)
                )
                self.assertEqual(data.image_url, '')

    def test_same_official_external_id_updates_instead_of_duplicates(self):
        first = PokemonKoreaCardCollector.normalize(self.fixture())
        second = PokemonKoreaCardCollector.normalize(self.fixture(rarity='C mirror'))

        first_result = import_cards([first])
        second_result = import_cards([second])

        self.assertEqual(first_result.created, 1)
        self.assertEqual(second_result.updated, 1)
        self.assertEqual(Card.objects.count(), 1)
        self.assertEqual(Card.objects.get().rarity, 'C mirror')

    def test_ambiguous_natural_key_without_external_id_is_skipped(self):
        common = {
            'name_ko': '피카츄',
            'set_name': '강화 확장팩 포켓몬 카드 151',
            'card_number': '025/165',
            'language': 'KO',
            'source': 'POKEMON_KOREA',
        }
        Card.objects.create(external_id='one', **common)
        Card.objects.create(external_id='two', **common)
        data = PokemonKoreaCardCollector.normalize(self.fixture(external_id='candidate'))
        data = type(data)(
            name_ko=data.name_ko,
            name_en=data.name_en,
            set_name=data.set_name,
            card_number=data.card_number,
            language=data.language,
            source=data.source,
            external_id=None,
            rarity=data.rarity,
            image_url=data.image_url,
        )

        result = import_cards([data])

        self.assertEqual(result.skipped, 1)
        self.assertEqual(Card.objects.count(), 2)

    def test_enabled_collector_has_hard_request_policy(self):
        collector = PokemonKoreaCardCollector()
        self.assertTrue(collector.HTTP_ENABLED)
        self.assertEqual(collector.REQUEST_POLICY.request_budget, 6)
        self.assertLessEqual(collector.REQUEST_POLICY.max_items, 3)
        self.assertEqual(collector.REQUEST_POLICY.retry_limit, 0)
        self.assertEqual(collector.REQUEST_POLICY.timeout_seconds, 10)


class DomesticMarketSafetyTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.base = {
            'external_id': 'listing-025',
            'title': '포켓몬 카드 151 피카츄 025/165',
            'price': '₩12,000',
            'url': 'https://example.com/listing/025',
            'image_url': 'https://example.com/listing/025.jpg',
            'collected_at': self.now,
        }

    def test_kream_confirmed_sold_requires_occurrence_time(self):
        with self.assertRaises(InvalidResponseError):
            KreamMarketCollector.normalize({
                **self.base,
                'data_type': 'SOLD',
                'transaction_confirmed': True,
            })

    def test_kream_asking_price_is_current_not_sold(self):
        data = KreamMarketCollector.normalize({
            **self.base,
            'data_type': 'CURRENT_LISTING',
        })
        self.assertEqual(data.listing_type, ListingType.CURRENT_LISTING)
        self.assertEqual(data.price, Decimal('12000'))

    def test_bunjang_never_promotes_completed_text_to_sold(self):
        with self.assertRaises(InvalidResponseError):
            BunjangMarketCollector.normalize({
                'pid': 12345, 'name': '피카츄 025/165', 'price': 12000,
                'saleStatus': 'SOLD',
            })

    def test_naver_auction_requires_final_price_and_time(self):
        for changes in (
            {'price': '', 'occurred_at': self.now},
            {'price': '12000'},
        ):
            with self.subTest(changes=changes), self.assertRaises(InvalidResponseError):
                NaverCafeCardmvkCollector.normalize({
                    **self.base,
                    **changes,
                    'board_type': 'AUCTION_RESULT',
                    'final_result_confirmed': True,
                })

    def test_naver_auction_is_not_sold(self):
        data = NaverCafeCardmvkCollector.normalize({
            **self.base,
            'board_type': 'AUCTION_RESULT',
            'final_result_confirmed': True,
            'occurred_at': self.now,
        })
        self.assertEqual(data.listing_type, ListingType.AUCTION_RESULT)
        self.assertNotEqual(data.listing_type, ListingType.SOLD)

    def test_seller_pii_fields_are_not_part_of_normalized_data(self):
        data = BunjangMarketCollector.normalize({
            'pid': 12345,
            'name': '피카츄 025/165',
            'price': 12000,
            'saleStatus': 'SELLING',
            'seller_name': 'not-stored',
            'seller_nickname': 'not-stored',
            'phone': 'not-stored',
            'address': 'not-stored',
        })
        for field_name in ('seller_name', 'seller_nickname', 'phone', 'address'):
            self.assertFalse(hasattr(data, field_name))

    def test_listing_image_stays_listing_metadata(self):
        data = BunjangMarketCollector.normalize({
            'pid': 12345,
            'name': '피카츄 025/165',
            'price': 12000,
            'saleStatus': 'SELLING',
            'imageUrlTemplate': 'https://media.bunjang.co.kr/product/12345_{cnt}_1_w640.jpg',
            'imageCount': 1,
        })
        self.assertEqual(
            data.image_url,
            'https://media.bunjang.co.kr/product/12345_1_1_w640.jpg',
        )

    @patch('requests.Session.request')
    def test_all_unapproved_collectors_stop_before_http(self, request):
        for collector in (
            KreamMarketCollector(),
            NaverCafeCardmvkCollector(),
        ):
            with self.subTest(source=collector.SOURCE), self.assertRaises(ExternalAPIError):
                collector.collect()
        request.assert_not_called()

    def test_disabled_market_collectors_have_bounded_policy(self):
        for collector in (
            KreamMarketCollector(),
            NaverCafeCardmvkCollector(),
        ):
            with self.subTest(source=collector.SOURCE):
                self.assertEqual(collector.REQUEST_POLICY.request_budget, 1)
                self.assertLessEqual(collector.REQUEST_POLICY.max_items, 3)
                self.assertEqual(collector.REQUEST_POLICY.retry_limit, 0)


class ConservativeKoreanMatcherTests(TestCase):
    def setUp(self):
        self.card = Card.objects.create(
            external_id='ko-025',
            name_ko='피카츄',
            name_en='Pikachu',
            set_name='포켓몬 카드 151',
            card_number='025/165',
            language='KO',
            source='POKEMON_KOREA',
        )

    def test_exact_korean_name_number_and_set_match(self):
        self.assertTrue(is_listing_relevant_to_card(
            self.card,
            '포켓몬 카드 151 피카츄 025/165 미품',
        ))

    def test_different_number_or_name_is_rejected(self):
        for title in ('피카츄 173/165', '리자몽 025/165'):
            with self.subTest(title=title):
                self.assertFalse(is_listing_relevant_to_card(self.card, title))

    def test_korean_bundle_random_and_bulk_signals_are_rejected(self):
        for title in (
            '피카츄 025/165 10장',
            '피카츄 025/165 랜덤',
            '피카츄 025/165 대량 묶음',
            '피카츄 025/165 풀세트',
        ):
            with self.subTest(title=title):
                self.assertFalse(is_listing_relevant_to_card(self.card, title))

    def test_ambiguous_candidates_are_not_guessed(self):
        second = Card.objects.create(
            external_id='ko-025-second',
            name_ko='피카츄',
            set_name='다른 포켓몬 카드 151',
            card_number='025/165',
            language='KO',
            source='POKEMON_KOREA',
        )
        self.assertIsNone(match_card('피카츄 025/165', [self.card, second]))

    def test_subjective_condition_is_not_converted_to_grade(self):
        for word in ('미품', '초미품', 'A급', 'S급'):
            result = classify_condition(
                f'피카츄 025/165 {word}',
                card_matched=True,
            )
            self.assertEqual(result.condition, Condition.RAW)
            self.assertIsNone(result.grading_company)
            self.assertIsNone(result.grading_score)
