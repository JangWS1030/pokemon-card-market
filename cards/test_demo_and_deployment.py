from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from cards.models import Card, Condition, MarketListing, MarketRegion, MarketSource, PriceHistory
from cards.services.demo_data import clear_demo_data, seed_demo_data
from config.env import env_bool, env_list


class DemoDataTests(TestCase):
    def test_seed_creates_explicit_demo_data(self):
        result = seed_demo_data()

        self.assertEqual(result.cards, 12)
        self.assertEqual(result.listings, 8)
        self.assertEqual(result.histories, 24)
        self.assertFalse(Card.objects.filter(source='DEMO').exclude(external_id__startswith='demo-card-').exists())
        self.assertEqual(MarketListing.objects.exclude(market_source__code='DEMO').count(), 0)

    def test_seed_is_idempotent(self):
        seed_demo_data()
        seed_demo_data()

        self.assertEqual(Card.objects.filter(source='DEMO').count(), 12)
        self.assertEqual(MarketListing.objects.filter(market_source__code='DEMO').count(), 8)
        self.assertEqual(PriceHistory.objects.filter(card__source='DEMO').count(), 24)

    def test_clear_deletes_only_demo_data(self):
        seed_demo_data()
        real_card = Card.objects.create(
            external_id='real-card', name_ko='실제 카드', set_name='실제 세트',
            card_number='1/1', language='KO', source='JUSTTCG',
        )
        real_source = MarketSource.objects.create(
            code='REAL', name='Real Market', market_region=MarketRegion.GLOBAL
        )
        MarketListing.objects.create(
            card=real_card, market_source=real_source, external_id='real-listing',
            title='Real listing', price=Decimal('1.00'), currency='USD',
            url='https://example.com/real', condition=Condition.RAW,
            collected_at=timezone.now(),
        )

        clear_demo_data()

        self.assertFalse(Card.objects.filter(source='DEMO').exists())
        self.assertTrue(Card.objects.filter(pk=real_card.pk, source='JUSTTCG').exists())
        self.assertTrue(MarketListing.objects.filter(external_id='real-listing').exists())

    def test_demo_badge_and_graph_data_are_rendered(self):
        seed_demo_data()
        card = Card.objects.get(external_id='demo-card-001')

        list_response = self.client.get(reverse('card-list'))
        detail_response = self.client.get(reverse('card-detail', args=[card.pk]))

        self.assertContains(list_response, 'DEMO · 테스트 데이터')
        self.assertContains(detail_response, '실제 시세가 아닙니다')
        self.assertContains(detail_response, 'price-chart-data')
        labels = {item['label'] for item in detail_response.context['price_chart_data']['datasets']}
        self.assertIn('RAW / USD', labels)
        self.assertIn('RAW / KRW', labels)
        self.assertIn('PSA 10.0 / USD', labels)


class EnvironmentParsingTests(TestCase):
    @patch.dict('os.environ', {'TEST_BOOL': 'false', 'TEST_LIST': 'a, b,,c'}, clear=False)
    def test_environment_values_are_parsed(self):
        self.assertFalse(env_bool('TEST_BOOL', default=True))
        self.assertEqual(env_list('TEST_LIST'), ['a', 'b', 'c'])

    @patch.dict('os.environ', {'TEST_BOOL': 'unexpected'}, clear=False)
    def test_invalid_boolean_uses_default(self):
        self.assertTrue(env_bool('TEST_BOOL', default=True))


class ErrorPageTests(TestCase):
    @override_settings(DEBUG=False)
    def test_custom_404_page(self):
        response = self.client.get('/missing-page/')

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, '페이지를 찾을 수 없습니다', status_code=404)
