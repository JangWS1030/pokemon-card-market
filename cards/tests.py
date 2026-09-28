from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .collectors import CardData
from .models import Card, Condition, MarketListing, MarketRegion, MarketSource, PriceHistory
from .services.card_importer import import_cards


class HomeViewTests(TestCase):
    def test_home_page_returns_successfully(self):
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'cards/home.html')
        self.assertContains(response, 'Pokemon Card Market')


class MarketModelTests(TestCase):
    def setUp(self):
        self.card = Card.objects.create(
            external_id='card-001',
            name_ko='리자몽 ex',
            name_en='Charizard ex',
            set_name='테스트 세트',
            card_number='201/165',
            rarity='SAR',
            language='KO',
            source='TEST_CARD_SOURCE',
        )
        self.market_source = MarketSource.objects.create(
            code='TEST_MARKET',
            name='테스트 판매처',
            market_region=MarketRegion.KR,
        )

    def test_card_is_created(self):
        self.assertEqual(Card.objects.count(), 1)
        self.assertEqual(str(self.card), '리자몽 ex / 테스트 세트 / 201/165')

    def test_market_source_is_created(self):
        self.assertEqual(MarketSource.objects.count(), 1)
        self.assertEqual(self.market_source.market_region, MarketRegion.KR)

    def test_market_listing_is_created(self):
        listing = MarketListing.objects.create(
            card=self.card,
            market_source=self.market_source,
            external_id='listing-001',
            title='리자몽 ex 201/165',
            price=120000,
            currency='KRW',
            url='https://example.com/listing-001',
            condition=Condition.RAW,
            collected_at=timezone.now(),
        )

        self.assertEqual(listing.card, self.card)
        self.assertEqual(listing.currency, 'KRW')

    def test_price_history_is_created(self):
        history = PriceHistory.objects.create(
            card=self.card,
            condition=Condition.RAW,
            calculated_at=timezone.now(),
            median_price=120000,
            average_price=121000,
            min_price=110000,
            max_price=130000,
            listing_count=5,
        )

        self.assertEqual(history.condition, Condition.RAW)
        self.assertEqual(history.listing_count, 5)

    def test_duplicate_card_source_and_external_id_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Card.objects.create(
                external_id='card-001',
                name_ko='중복 카드',
                set_name='다른 세트',
                card_number='001/100',
                language='KO',
                source='TEST_CARD_SOURCE',
            )

    def test_cards_without_external_id_can_be_created(self):
        Card.objects.create(
            name_ko='ID 없는 카드 1',
            set_name='테스트 세트',
            card_number='001/100',
            language='KO',
            source='TEST_CARD_SOURCE',
        )
        Card.objects.create(
            name_ko='ID 없는 카드 2',
            set_name='테스트 세트',
            card_number='002/100',
            language='KO',
            source='TEST_CARD_SOURCE',
        )

        self.assertEqual(Card.objects.filter(external_id__isnull=True).count(), 2)

    def test_duplicate_market_listing_is_rejected(self):
        listing_data = {
            'card': self.card,
            'market_source': self.market_source,
            'external_id': 'listing-duplicate',
            'title': '중복 확인 상품',
            'price': 120000,
            'currency': 'KRW',
            'url': 'https://example.com/listing-duplicate',
            'condition': Condition.RAW,
            'collected_at': timezone.now(),
        }
        MarketListing.objects.create(**listing_data)

        with self.assertRaises(IntegrityError), transaction.atomic():
            MarketListing.objects.create(**listing_data)

    def test_raw_and_psa_10_histories_are_stored_separately(self):
        PriceHistory.objects.create(
            card=self.card,
            condition=Condition.RAW,
            calculated_at=timezone.now(),
            median_price=120000,
            average_price=120000,
            min_price=120000,
            max_price=120000,
            listing_count=1,
        )
        PriceHistory.objects.create(
            card=self.card,
            condition=Condition.PSA,
            grading_score=Decimal('10.0'),
            calculated_at=timezone.now(),
            median_price=500000,
            average_price=500000,
            min_price=500000,
            max_price=500000,
            listing_count=1,
        )

        raw_history = PriceHistory.objects.get(condition=Condition.RAW)
        psa_history = PriceHistory.objects.get(condition=Condition.PSA)

        self.assertIsNone(raw_history.grading_score)
        self.assertEqual(psa_history.grading_score, Decimal('10.0'))
        self.assertEqual(PriceHistory.objects.count(), 2)


class CardImportServiceTests(TestCase):
    def make_card_data(self, **changes):
        values = {
            'external_id': 'external-001',
            'name_ko': '피카츄',
            'name_en': 'Pikachu',
            'set_name': '테스트 세트',
            'card_number': '001/100',
            'rarity': 'AR',
            'language': 'ko',
            'image_url': 'https://example.com/pikachu.jpg',
            'source': 'TEST_CARD_SOURCE',
        }
        values.update(changes)
        return CardData(**values)

    def test_new_card_is_created(self):
        result = import_cards([self.make_card_data()])

        self.assertEqual(result.created, 1)
        self.assertEqual(Card.objects.count(), 1)
        self.assertEqual(Card.objects.get().language, 'KO')

    def test_same_source_and_external_id_updates_existing_card(self):
        import_cards([self.make_card_data(rarity='AR')])
        result = import_cards([self.make_card_data(rarity='SR')])

        self.assertEqual(result.updated, 1)
        self.assertEqual(Card.objects.count(), 1)
        self.assertEqual(Card.objects.get().rarity, 'SR')

    def test_card_without_external_id_uses_natural_fields(self):
        import_cards([self.make_card_data(external_id=None, rarity='AR')])
        result = import_cards([self.make_card_data(external_id=None, rarity='SR')])

        self.assertEqual(result.updated, 1)
        self.assertEqual(Card.objects.count(), 1)
        self.assertEqual(Card.objects.get().rarity, 'SR')

    def test_missing_required_value_is_skipped(self):
        result = import_cards([self.make_card_data(name_ko='  ', name_en=None)])

        self.assertEqual(result.skipped, 1)
        self.assertEqual(Card.objects.count(), 0)
        self.assertIn('name_ko 또는 name_en 중 하나는 필요합니다.', result.messages[0])

    def test_ambiguous_candidates_are_not_selected(self):
        common_values = {
            'name_ko': '피카츄',
            'set_name': '테스트 세트',
            'card_number': '001/100',
            'language': 'KO',
        }
        Card.objects.create(
            **common_values,
            external_id='first',
            source='TEST_CARD_SOURCE',
        )
        Card.objects.create(
            **common_values,
            external_id='second',
            source='TEST_CARD_SOURCE',
        )

        result = import_cards([self.make_card_data(external_id=None)])

        self.assertEqual(result.skipped, 1)
        self.assertEqual(Card.objects.count(), 2)

    def test_natural_fields_do_not_match_a_different_source(self):
        Card.objects.create(
            external_id='demo-card',
            name_ko='데모 카드',
            name_en='Pikachu',
            set_name='테스트 세트',
            card_number='001/100',
            language='UNKNOWN',
            source='DEMO',
        )

        result = import_cards([
            self.make_card_data(
                external_id=None,
                name_ko='',
                language='UNKNOWN',
                source='JUSTTCG',
            )
        ])

        self.assertEqual(result.created, 1)
        self.assertEqual(Card.objects.filter(source='DEMO').count(), 1)
        self.assertEqual(Card.objects.filter(source='JUSTTCG').count(), 1)

    def test_import_command_does_not_insert_sample_data(self):
        output = StringIO()

        call_command('import_cards', stdout=output)

        self.assertIn('사용 가능한 카드 데이터 Collector가 아직 설정되지 않았습니다.', output.getvalue())
        self.assertEqual(Card.objects.count(), 0)


class CardPageTests(TestCase):
    def setUp(self):
        self.card = Card.objects.create(
            external_id='page-card-001',
            name_ko='리자몽 ex',
            name_en='Charizard ex',
            set_name='테스트 세트',
            card_number='201/165',
            rarity='SAR',
            language='KO',
            source='TEST_CARD_SOURCE',
        )

    def test_card_list_returns_successfully(self):
        response = self.client.get(reverse('card-list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '리자몽 ex')

    def test_card_is_shown_in_list(self):
        response = self.client.get(reverse('card-list'))

        self.assertContains(response, self.card.name_ko)
        self.assertContains(response, self.card.card_number)

    def test_searches_korean_name(self):
        response = self.client.get(reverse('card-list'), {'q': '리자몽'})

        self.assertContains(response, self.card.name_ko)

    def test_searches_english_name(self):
        response = self.client.get(reverse('card-list'), {'q': 'charizard'})

        self.assertContains(response, self.card.name_ko)

    def test_searches_card_number(self):
        response = self.client.get(reverse('card-list'), {'q': '201/165'})

        self.assertContains(response, self.card.name_ko)

    def test_existing_card_detail_returns_successfully(self):
        response = self.client.get(reverse('card-detail', args=[self.card.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.card.name_ko)
        self.assertContains(response, self.card.source)

    def test_missing_card_detail_returns_404(self):
        response = self.client.get(reverse('card-detail', args=[999999]))

        self.assertEqual(response.status_code, 404)

    def test_card_detail_without_prices_is_safe(self):
        response = self.client.get(reverse('card-detail', args=[self.card.pk]))

        self.assertContains(response, 'eBay 현재 매물 데이터가 없습니다.')
        self.assertContains(response, '국내 판매완료 데이터는 아직 연결되지 않았습니다.')
        self.assertContains(response, '아직 계산된 참고 가격이 없습니다.')

    def test_english_name_is_used_when_korean_name_is_empty(self):
        self.card.name_ko = ''
        self.card.save(update_fields=['name_ko'])

        list_response = self.client.get(reverse('card-list'))
        detail_response = self.client.get(reverse('card-detail', args=[self.card.pk]))

        self.assertContains(list_response, 'Charizard ex')
        self.assertContains(detail_response, 'Charizard ex')

    def test_card_detail_with_market_listing(self):
        market_source = MarketSource.objects.create(
            code='DETAIL_MARKET',
            name='상세 테스트 판매처',
            market_region=MarketRegion.KR,
        )
        MarketListing.objects.create(
            card=self.card,
            market_source=market_source,
            external_id='detail-listing',
            title='상세 화면 테스트 상품',
            price=120000,
            currency='KRW',
            url='https://example.com/detail-listing',
            condition=Condition.RAW,
            collected_at=timezone.now(),
        )

        response = self.client.get(reverse('card-detail', args=[self.card.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, market_source.name)
        self.assertContains(response, 'KRW')
        self.assertContains(response, '최근 가격 수집')

    def test_card_detail_with_price_history(self):
        PriceHistory.objects.create(
            card=self.card,
            condition=Condition.PSA,
            grading_score=Decimal('10.0'),
            calculated_at=timezone.now(),
            median_price=500000,
            average_price=510000,
            min_price=490000,
            max_price=530000,
            listing_count=4,
        )

        response = self.client.get(reverse('card-detail', args=[self.card.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '현재 매물 중앙값')
        self.assertContains(response, '최근 참고가 계산')
        self.assertContains(response, 'PSA 10.0')

    def test_card_list_uses_pagination(self):
        for number in range(2, 26):
            Card.objects.create(
                external_id=f'page-card-{number:03d}',
                name_ko=f'테스트 카드 {number:02d}',
                set_name='페이지 테스트 세트',
                card_number=f'{number:03d}/100',
                language='KO',
                source='TEST_CARD_SOURCE',
            )

        first_page = self.client.get(reverse('card-list'))
        second_page = self.client.get(reverse('card-list'), {'page': 2})

        self.assertEqual(len(first_page.context['page_obj']), 24)
        self.assertEqual(len(second_page.context['page_obj']), 1)

    def test_search_query_is_kept_in_pagination_links(self):
        for number in range(2, 27):
            Card.objects.create(
                external_id=f'search-page-{number}',
                name_ko=f'리자몽 테스트 {number}',
                set_name='검색 세트',
                card_number=f'{number:03d}/100',
                language='KO',
                source='TEST_CARD_SOURCE',
            )

        response = self.client.get(reverse('card-list'), {'q': '리자몽'})

        self.assertContains(response, 'q=%EB%A6%AC%EC%9E%90%EB%AA%BD&amp;page=2')


class EmptyCardPageTests(TestCase):
    def test_home_with_empty_database_returns_successfully(self):
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '등록된 카드가 없습니다.')

    def test_card_list_with_empty_database_returns_successfully(self):
        response = self.client.get(reverse('card-list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '검색 결과가 없습니다.')
