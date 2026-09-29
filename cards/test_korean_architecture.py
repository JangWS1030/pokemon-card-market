from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cards.collectors import ExternalAPIError, InvalidResponseError, MissingCredentialsError
from cards.collectors.card_data import PokemonKoreaCardCollector
from cards.collectors.markets import (
    BunjangMarketCollector,
    EbayMarketCollector,
    KreamMarketCollector,
    NaverCafeCardmvkCollector,
)
from cards.models import (
    Card,
    Condition,
    ListingType,
    MarketListing,
    MarketRegion,
    MarketSource,
    PriceHistory,
)
from cards.services.card_importer import import_cards
from cards.services.card_matching import is_listing_relevant_to_card
from cards.services.condition_classifier import ConditionResult
from cards.services.condition_classifier import classify_condition
from cards.services.market_importer import save_market_listing
from cards.services.normalization import contains_card_number
from cards.services.price_calculator import calculate_price_groups
from cards.services.price_history import save_price_histories


class PokemonKoreaCardArchitectureTests(TestCase):
    def fixture(self, **changes):
        values = {
            'external_id': 'PK-KO-025',
            'name_ko': '피카츄',
            'set_name': '강화 확장팩 포켓몬 카드 151',
            'card_number': '025/165',
            'rarity': 'C',
            'image_url': 'https://cards.image.pokemonkorea.co.kr/example.png',
        }
        values.update(changes)
        return values

    def test_normalized_korean_card_is_importer_compatible(self):
        data = PokemonKoreaCardCollector.normalize(self.fixture())
        result = import_cards([data])
        card = Card.objects.get()
        self.assertEqual(result.created, 1)
        self.assertEqual(card.name_ko, '피카츄')
        self.assertEqual(card.language, 'KO')
        self.assertEqual(card.source, 'POKEMON_KOREA')

    def test_korean_card_keeps_public_image_url(self):
        data = PokemonKoreaCardCollector.normalize(self.fixture())
        self.assertEqual(data.image_url, self.fixture()['image_url'])

    def test_invalid_korean_card_image_is_not_guessed(self):
        data = PokemonKoreaCardCollector.normalize(
            self.fixture(image_url='javascript:guess-image')
        )
        self.assertEqual(data.image_url, '')

    def test_http_collection_requires_explicit_public_detail_url(self):
        collector = PokemonKoreaCardCollector()
        self.assertTrue(collector.HTTP_ENABLED)
        self.assertFalse(hasattr(collector, 'search'))
        self.assertEqual(collector.REQUEST_POLICY.retry_limit, 0)

    def test_korean_card_source_attribution_and_image_render(self):
        import_cards([PokemonKoreaCardCollector.normalize(self.fixture())])
        response = self.client.get(reverse('card-detail', args=[Card.objects.get().pk]))
        self.assertContains(response, 'Pokémon Card Game Korea')
        self.assertContains(response, self.fixture()['image_url'])

    def test_korean_card_without_image_has_specific_placeholder(self):
        import_cards([PokemonKoreaCardCollector.normalize(self.fixture(image_url=''))])
        response = self.client.get(reverse('card-detail', args=[Card.objects.get().pk]))
        self.assertContains(response, '한국판 카드 대표 이미지 준비 중')


class KoreanCardMatchingTests(TestCase):
    def setUp(self):
        self.card = Card.objects.create(
            external_id='ko-pikachu',
            name_ko='피카츄 - 025/165',
            name_en='Pikachu',
            set_name='포켓몬 카드 151',
            card_number='025/165',
            language='KO',
            source='POKEMON_KOREA',
        )

    def test_korean_spacing_hyphen_and_hash_share_card_number(self):
        for text in ('피카츄 025 / 165', '피카츄 - 025/165', '피카츄 #025/165'):
            with self.subTest(text=text):
                self.assertTrue(contains_card_number(text, self.card.card_number))

    def test_same_korean_name_and_number_matches(self):
        self.assertTrue(is_listing_relevant_to_card(self.card, '피카츄 025/165 미품'))

    def test_different_number_is_rejected(self):
        self.assertFalse(is_listing_relevant_to_card(self.card, '피카츄 173/165 미품'))

    def test_different_korean_name_with_same_number_is_rejected(self):
        self.assertFalse(is_listing_relevant_to_card(self.card, '리자몽 025/165 미품'))

    def test_numberless_listing_without_set_is_rejected(self):
        self.assertFalse(is_listing_relevant_to_card(self.card, '피카츄 초미품'))

    def test_numberless_listing_with_full_set_signal_is_allowed(self):
        self.assertTrue(is_listing_relevant_to_card(self.card, '포켓몬 카드 151 피카츄 초미품'))

    def test_clear_korean_unopened_signal_is_sealed(self):
        self.assertEqual(
            classify_condition('피카츄 025/165 미개봉', card_matched=True).condition,
            Condition.SEALED,
        )


class KoreanMarketFixtureTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.base = {
            'external_id': 'fixture-1',
            'title': '피카츄 025/165',
            'price': '12000',
            'url': 'https://example.com/listing/1',
            'image_url': 'https://example.com/listing/1.jpg',
            'collected_at': self.now,
        }

    def test_kream_current_listing_fixture(self):
        data = KreamMarketCollector.normalize({**self.base, 'data_type': 'CURRENT_LISTING'})
        self.assertEqual((data.source, data.currency, data.listing_type), (
            'KREAM', 'KRW', ListingType.CURRENT_LISTING
        ))

    def test_kream_confirmed_sold_fixture_keeps_occurrence_time(self):
        data = KreamMarketCollector.normalize({
            **self.base,
            'data_type': 'SOLD',
            'transaction_confirmed': True,
            'occurred_at': self.now,
        })
        self.assertEqual(data.listing_type, ListingType.SOLD)
        self.assertEqual(data.occurred_at, self.now)

    def test_kream_unconfirmed_sold_is_rejected(self):
        with self.assertRaises(InvalidResponseError):
            KreamMarketCollector.normalize({**self.base, 'data_type': 'SOLD'})

    def test_bunjang_current_listing_fixture(self):
        data = BunjangMarketCollector.normalize({
            'pid': 12345,
            'name': '피카츄 025/165',
            'price': 12000,
            'saleStatus': 'SELLING',
        })
        self.assertEqual(data.listing_type, ListingType.CURRENT_LISTING)

    def test_bunjang_sold_text_does_not_create_fake_sold(self):
        with self.assertRaises(InvalidResponseError):
            BunjangMarketCollector.normalize({
                'pid': 12345, 'name': '피카츄 025/165', 'price': 12000,
                'saleStatus': 'SOLD',
            })

    def test_naver_trade_fixture_is_current_listing(self):
        data = NaverCafeCardmvkCollector.normalize({**self.base, 'board_type': 'TRADE'})
        self.assertEqual(data.listing_type, ListingType.CURRENT_LISTING)

    def test_naver_confirmed_auction_fixture_is_not_sold(self):
        data = NaverCafeCardmvkCollector.normalize({
            **self.base,
            'board_type': 'AUCTION_RESULT',
            'final_result_confirmed': True,
            'occurred_at': self.now,
        })
        self.assertEqual(data.listing_type, ListingType.AUCTION_RESULT)
        self.assertNotEqual(data.listing_type, ListingType.SOLD)

    def test_naver_unconfirmed_auction_result_is_rejected(self):
        with self.assertRaises(InvalidResponseError):
            NaverCafeCardmvkCollector.normalize({
                **self.base, 'board_type': 'AUCTION_RESULT'
            })

    def test_unapproved_domestic_http_collectors_are_disabled(self):
        for collector in (
            KreamMarketCollector(),
            NaverCafeCardmvkCollector(),
        ):
            with self.subTest(source=collector.SOURCE), self.assertRaises(ExternalAPIError):
                collector.collect()

    def test_bunjang_official_api_requires_credentials_before_http(self):
        with self.assertRaises(MissingCredentialsError):
            BunjangMarketCollector(access_key='', secret_key='').collect('피카츄', 1)


class ListingTypeAndPriceSeparationTests(TestCase):
    def setUp(self):
        self.card = Card.objects.create(
            external_id='ko-price-card',
            name_ko='피카츄',
            set_name='포켓몬 카드 151',
            card_number='025/165',
            language='KO',
            source='POKEMON_KOREA',
        )

    def listing(self, price, currency, listing_type):
        return SimpleNamespace(
            card_id=self.card.pk,
            condition=Condition.RAW,
            grading_score=None,
            currency=currency,
            listing_type=listing_type,
            price=Decimal(price),
            is_active=True,
        )

    def test_listing_type_choices_cover_three_distinct_meanings(self):
        self.assertEqual(
            set(ListingType.values),
            {'CURRENT_LISTING', 'SOLD', 'AUCTION_RESULT'},
        )

    def test_market_source_supports_korean_sources_without_model_change(self):
        for code, name in (
            ('KREAM', 'KREAM'),
            ('BUNJANG', '번개장터'),
            ('NAVER_CARDMVK', '카드마켓 네이버 카페'),
        ):
            MarketSource.objects.create(code=code, name=name, market_region=MarketRegion.KR)
        self.assertEqual(MarketSource.objects.filter(market_region=MarketRegion.KR).count(), 3)

    def test_price_groups_separate_currency_and_listing_type(self):
        calculations = calculate_price_groups([
            self.listing('10000', 'KRW', ListingType.CURRENT_LISTING),
            self.listing('9000', 'KRW', ListingType.SOLD),
            self.listing('8500', 'KRW', ListingType.AUCTION_RESULT),
            self.listing('5', 'USD', ListingType.CURRENT_LISTING),
        ])
        self.assertEqual(len(calculations), 4)
        self.assertEqual(
            {(item.listing_type, item.currency) for item in calculations},
            {
                (ListingType.CURRENT_LISTING, 'KRW'),
                (ListingType.SOLD, 'KRW'),
                (ListingType.AUCTION_RESULT, 'KRW'),
                (ListingType.CURRENT_LISTING, 'USD'),
            },
        )

    def test_price_histories_persist_separate_listing_types(self):
        calculations = calculate_price_groups([
            self.listing('10000', 'KRW', ListingType.CURRENT_LISTING),
            self.listing('9000', 'KRW', ListingType.SOLD),
            self.listing('8500', 'KRW', ListingType.AUCTION_RESULT),
        ])
        save_price_histories(calculations)
        self.assertEqual(
            set(PriceHistory.objects.values_list('listing_type', flat=True)),
            {ListingType.CURRENT_LISTING, ListingType.SOLD, ListingType.AUCTION_RESULT},
        )

    def test_domestic_ui_keeps_sold_current_and_auction_sections_separate(self):
        common = {
            'card': self.card,
            'condition': Condition.RAW,
            'currency': 'KRW',
            'calculated_at': timezone.now(),
            'median_price': 10000,
            'average_price': 10000,
            'min_price': 10000,
            'max_price': 10000,
            'listing_count': 1,
        }
        for listing_type in ListingType.values:
            PriceHistory.objects.create(listing_type=listing_type, **common)

        response = self.client.get(reverse('card-detail', args=[self.card.pk]))
        self.assertEqual(len(response.context['domestic_sold_histories']), 1)
        self.assertEqual(len(response.context['domestic_current_histories']), 1)
        self.assertEqual(len(response.context['auction_result_histories']), 1)

    def test_existing_style_ebay_market_data_defaults_to_current_listing(self):
        data = EbayMarketCollector('id', 'secret').normalize({
            'itemId': 'ebay-1',
            'title': 'Pokemon Pikachu 025/165',
            'price': {'value': '4.99', 'currency': 'USD'},
            'itemWebUrl': 'https://www.ebay.com/itm/ebay-1',
        })
        self.assertEqual(data.listing_type, ListingType.CURRENT_LISTING)

    def test_card_image_and_listing_image_remain_separate(self):
        source = MarketSource.objects.create(
            code='KREAM', name='KREAM', market_region=MarketRegion.KR
        )
        data = KreamMarketCollector.normalize({
            'external_id': 'kream-image',
            'title': '피카츄 025/165',
            'price': '12000',
            'url': 'https://example.com/listing/kream-image',
            'image_url': 'https://example.com/listing-image.jpg',
            'collected_at': timezone.now(),
            'data_type': 'CURRENT_LISTING',
        })
        listing = save_market_listing(
            data,
            self.card,
            source,
            ConditionResult(condition=Condition.RAW),
        ).listing
        self.card.refresh_from_db()
        self.assertEqual(listing.image_url, 'https://example.com/listing-image.jpg')
        self.assertFalse(self.card.image_url)

    def test_korean_price_sections_precede_overseas_reference(self):
        response = self.client.get(reverse('card-detail', args=[self.card.pk]))
        content = response.content.decode()
        self.assertLess(content.index('국내 실거래'), content.index('해외 참고 · eBay 현재 매물'))
