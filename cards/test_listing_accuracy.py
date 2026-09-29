from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cards.collectors import MarketData
from cards.collectors.markets import EbayMarketCollector
from cards.models import Card, Condition, MarketListing, MarketRegion, MarketSource, PriceHistory
from cards.services.card_matching import is_listing_relevant_to_card
from cards.services.condition_classifier import classify_condition
from cards.services.market_importer import save_market_listing
from cards.services.market_search import build_ebay_search_query


class QueryAndRelevanceTests(TestCase):
    def make_card(self, name='Pikachu - 025/165', number='025/165'):
        return Card.objects.create(
            external_id=f'card-{Card.objects.count()}',
            name_ko='',
            name_en=name,
            set_name='SV: Scarlet & Violet 151',
            card_number=number,
            rarity='Common',
            language='UNKNOWN',
            source='JUSTTCG',
        )

    def test_query_does_not_repeat_number_already_in_hyphenated_name(self):
        query = build_ebay_search_query(self.make_card())
        self.assertEqual(query, 'Pikachu - 025/165 SV: Scarlet & Violet 151 Pokemon')
        self.assertEqual(query.count('025/165'), 1)

    def test_query_adds_number_when_name_does_not_contain_it(self):
        query = build_ebay_search_query(self.make_card(name='Pikachu'))
        self.assertEqual(query, 'Pikachu 025/165 SV: Scarlet & Violet 151 Pokemon')

    def test_query_does_not_repeat_plain_number_in_name(self):
        query = build_ebay_search_query(self.make_card(name='Pikachu 025/165'))
        self.assertEqual(query.count('025/165'), 1)

    def test_query_does_not_repeat_hash_number_in_name(self):
        query = build_ebay_search_query(self.make_card(name='Pikachu #025/165'))
        self.assertEqual(query.count('025/165'), 1)

    def test_query_with_empty_number_uses_name_set_and_pokemon(self):
        query = build_ebay_search_query(self.make_card(name='Pikachu', number=''))
        self.assertEqual(query, 'Pikachu SV: Scarlet & Violet 151 Pokemon')

    def test_display_name_with_number_does_not_duplicate_existing_number(self):
        self.assertEqual(self.make_card().display_name_with_number, 'Pikachu - 025/165')

    def test_same_name_and_number_is_relevant(self):
        card = self.make_card()
        self.assertTrue(
            is_listing_relevant_to_card(card, 'Pokemon Pikachu 025/165 Scarlet Violet 151')
        )

    def test_different_card_number_is_rejected(self):
        card = self.make_card()
        self.assertFalse(is_listing_relevant_to_card(card, 'Pikachu 173/165 Pokemon 151'))

    def test_different_name_with_same_number_is_rejected(self):
        card = self.make_card()
        self.assertFalse(is_listing_relevant_to_card(card, 'Charizard 025/165 Pokemon 151'))

    def test_matching_name_without_number_remains_relevant(self):
        card = self.make_card()
        self.assertTrue(is_listing_relevant_to_card(card, 'Pokemon 151 Pikachu Near Mint'))

    def test_bundle_and_lot_signals_are_rejected(self):
        card = self.make_card()
        titles = (
            'Pikachu 025/165 lot of 10',
            'Pikachu 025/165 10 cards',
            'Pikachu 025/165 bundle',
            'Pikachu 025/165 random card',
            'Pikachu 025/165 complete set',
            'Pikachu 025/165 you pick',
        )
        for title in titles:
            with self.subTest(title=title):
                self.assertFalse(is_listing_relevant_to_card(card, title))
                self.assertEqual(classify_condition(title, card_matched=True).condition, Condition.UNKNOWN)

    @patch('cards.management.commands.import_ebay_once.EbayMarketCollector')
    def test_command_log_uses_nonduplicated_card_display(self, collector_class):
        self.make_card()
        collector_class.return_value.is_configured = True
        collector_class.return_value.collect.return_value = []
        output = StringIO()
        environment = {
            'EBAY_CLIENT_ID': 'mock-id',
            'EBAY_CLIENT_SECRET': 'mock-secret',
            'EBAY_IMPORT_CARD_SOURCE': 'JUSTTCG',
            'EBAY_IMPORT_CARD_NUMBER': '025/165',
            'EBAY_IMPORT_CARD_SET': 'SV: Scarlet & Violet 151',
            'EBAY_IMPORT_LIMIT': '3',
        }
        with patch.dict('os.environ', environment, clear=True):
            call_command('import_ebay_once', stdout=output)
        self.assertIn('Card: Pikachu - 025/165', output.getvalue())
        self.assertNotIn('025/165 025/165', output.getvalue())


class ListingImageAndDetailTests(TestCase):
    def setUp(self):
        self.card = Card.objects.create(
            external_id='image-card',
            name_ko='',
            name_en='Pikachu - 025/165',
            set_name='SV: Scarlet & Violet 151',
            card_number='025/165',
            rarity='Common',
            language='UNKNOWN',
            source='JUSTTCG',
        )
        self.source = MarketSource.objects.create(
            code='EBAY',
            name='eBay',
            base_url='https://www.ebay.com',
            market_region=MarketRegion.GLOBAL,
        )

    def raw_item(self, image=None):
        item = {
            'itemId': 'v1|image-item|0',
            'title': 'Pokemon Pikachu 025/165 Near Mint',
            'price': {'value': '4.99', 'currency': 'USD'},
            'itemWebUrl': 'https://www.ebay.com/itm/image-item',
        }
        if image is not None:
            item['image'] = image
        return item

    def save_listing(self, image_url=''):
        data = MarketData(
            external_id='image-item',
            title='Pokemon Pikachu 025/165 Near Mint',
            price=Decimal('4.99'),
            currency='USD',
            url='https://www.ebay.com/itm/image-item',
            collected_at=timezone.now(),
            source='EBAY',
            image_url=image_url,
        )
        return save_market_listing(
            data,
            self.card,
            self.source,
            classify_condition(data.title, card_matched=True),
        ).listing

    def test_collector_reads_browse_image_image_url(self):
        result = EbayMarketCollector('id', 'secret').normalize(
            self.raw_item({'imageUrl': 'https://i.ebayimg.com/images/example.jpg'})
        )
        self.assertEqual(result.image_url, 'https://i.ebayimg.com/images/example.jpg')

    def test_collector_uses_empty_image_when_image_is_missing(self):
        result = EbayMarketCollector('id', 'secret').normalize(self.raw_item())
        self.assertEqual(result.image_url, '')

    def test_collector_uses_empty_image_for_invalid_image_url(self):
        result = EbayMarketCollector('id', 'secret').normalize(
            self.raw_item({'imageUrl': 'javascript:alert(1)'})
        )
        self.assertEqual(result.image_url, '')

    def test_long_image_url_is_saved_without_truncation(self):
        image_url = 'https://i.ebayimg.com/images/example.jpg?' + ('key=value&' * 150)
        listing = self.save_listing(image_url)
        listing.refresh_from_db()
        self.assertEqual(listing.image_url, image_url)
        self.assertEqual(MarketListing._meta.get_field('image_url').max_length, 2048)

    def test_existing_listing_without_image_uses_empty_default(self):
        listing = self.save_listing()
        self.assertEqual(listing.image_url, '')
        response = self.client.get(reverse('card-detail', args=[self.card.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '이미지 없음')

    def test_listing_thumbnail_has_alt_and_lazy_loading(self):
        image_url = 'https://i.ebayimg.com/images/example.jpg'
        self.save_listing(image_url)
        response = self.client.get(reverse('card-detail', args=[self.card.pk]))
        self.assertContains(response, f'src="{image_url}"', html=False)
        self.assertContains(response, 'alt="Pokemon Pikachu 025/165 Near Mint 매물 이미지"')
        self.assertContains(response, 'loading="lazy"')

    def test_listing_title_and_secure_external_link_are_rendered(self):
        self.save_listing()
        response = self.client.get(reverse('card-detail', args=[self.card.pk]))
        self.assertContains(response, 'Pokemon Pikachu 025/165 Near Mint')
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'rel="noopener noreferrer"')

    def test_card_image_placeholder_is_distinct_from_listing_image(self):
        self.save_listing('https://i.ebayimg.com/images/example.jpg')
        response = self.client.get(reverse('card-detail', args=[self.card.pk]))
        self.assertContains(response, '카드 대표 이미지 준비 중')

    def test_current_listing_price_language_and_stats_are_rendered(self):
        PriceHistory.objects.create(
            card=self.card,
            condition=Condition.RAW,
            currency='USD',
            calculated_at=timezone.now(),
            median_price=Decimal('4.76'),
            average_price=Decimal('3.75'),
            min_price=Decimal('1.49'),
            max_price=Decimal('4.99'),
            listing_count=3,
        )
        response = self.client.get(reverse('card-detail', args=[self.card.pk]))
        for text in (
            '해외 참고 · eBay 현재 매물',
            '현재 매물 중앙값',
            'eBay 해외 CURRENT_LISTING 데이터만 기준으로 계산',
            '판매완료 가격이나 국내 실거래 시세가 아닙니다.',
            '유형별 가격 변화',
        ):
            with self.subTest(text=text):
                self.assertContains(response, text)
        self.assertContains(response, '$4.76')
        self.assertContains(response, '데이터 3건')
