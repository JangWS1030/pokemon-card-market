from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase

from cards.collectors import CardData
from cards.collectors.card_data import JustTCGCardCollector, JustTCGError, JustTCGReport
from cards.models import Card, MarketListing, PriceHistory
from cards.services.card_importer import import_cards


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


def justtcg_payload():
    return {
        'data': [
            {
                'id': 'pokemon-test-set-pikachu-25-common',
                'uuid': '11111111-1111-5111-8111-111111111111',
                'name': 'Pikachu',
                'game': 'Pokemon',
                'set': 'test-set-pokemon',
                'set_name': 'Test Set',
                'number': '25/100',
                'rarity': 'Common',
                'variants': [
                    {
                        'uuid': '22222222-2222-5222-8222-222222222222',
                        'language': 'Korean',
                        'condition': 'Near Mint',
                        'price': 1.23,
                    }
                ],
            },
            {
                'id': 'pokemon-test-set-eevee-26-common',
                'uuid': '33333333-3333-5333-8333-333333333333',
                'name': 'Eevee',
                'game': 'Pokemon',
                'set': 'test-set-pokemon',
                'set_name': 'Test Set',
                'number': '26/100',
                'rarity': 'Common',
                'variants': [
                    {
                        'uuid': '44444444-4444-5444-8444-444444444444',
                        'language': 'English',
                        'condition': 'Near Mint',
                    }
                ],
            },
        ],
        'meta': {'total': 100, 'limit': 2, 'offset': 0, 'hasMore': True},
        '_metadata': {'apiPlan': 'Free', 'apiRequestsRemaining': 999},
    }


class JustTCGCollectorTests(TestCase):
    def test_collects_base_cards_with_and_without_korean_variants(self):
        session = Mock()
        session.get.return_value = FakeResponse(payload=justtcg_payload())
        collector = JustTCGCardCollector(api_key='mock-key', session=session)

        cards = collector.collect(limit=2, query='Pikachu')

        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0].external_id, '11111111-1111-5111-8111-111111111111')
        self.assertEqual(cards[0].name_ko, '')
        self.assertEqual(cards[0].name_en, 'Pikachu')
        self.assertEqual(cards[0].language, 'KO')
        self.assertEqual(cards[1].name_ko, '')
        self.assertEqual(cards[1].name_en, 'Eevee')
        self.assertEqual(cards[1].language, 'UNKNOWN')
        self.assertIsNone(cards[0].image_url)
        params = session.get.call_args.kwargs['params']
        self.assertEqual(params['game'], 'pokemon')
        self.assertNotIn('language', params)
        self.assertEqual(params['limit'], 2)
        self.assertEqual(params['q'], 'Pikachu')
        self.assertEqual(params['offset'], 0)
        session.get.assert_called_once()
        self.assertEqual(collector.last_report.korean_variant_cards, 1)
        self.assertEqual(collector.last_report.without_korean_variant, 1)
        self.assertTrue(collector.last_report.card_summaries[0]['has_korean_variant'])
        self.assertFalse(collector.last_report.card_summaries[1]['has_korean_variant'])

    def test_pikachu_cards_without_variants_are_kept_and_non_cards_are_excluded(self):
        payload = {
            'data': [
                {
                    'uuid': 'ea180f3a-8c13-59b6-b887-c5cf9f7be4dd',
                    'name': 'Pikachu',
                    'game': 'Pokemon',
                    'set': 'sv-scarlet-violet-151-pokemon',
                    'set_name': 'SV: Scarlet & Violet 151',
                    'number': '025/165',
                    'rarity': 'Common',
                    'variants': [],
                },
                {
                    'uuid': '4de18046-39c2-572f-8b4c-c8371db5836f',
                    'name': 'Pikachu',
                    'game': 'Pokemon',
                    'set': 'sv-scarlet-violet-151-pokemon',
                    'set_name': 'SV: Scarlet & Violet 151',
                    'number': '173/165',
                    'rarity': 'Illustration Rare',
                    'variants': [],
                },
                {
                    'uuid': 'sealed-with-na',
                    'name': 'Booster Bundle',
                    'game': 'Pokemon',
                    'set': 'sv-scarlet-violet-151-pokemon',
                    'set_name': 'SV: Scarlet & Violet 151',
                    'number': 'N/A',
                    'variants': [],
                },
                {
                    'uuid': 'sealed-without-number',
                    'name': 'Elite Trainer Box',
                    'game': 'Pokemon',
                    'set': 'sv-scarlet-violet-151-pokemon',
                    'set_name': 'SV: Scarlet & Violet 151',
                    'variants': [],
                },
            ]
        }
        session = Mock()
        session.get.return_value = FakeResponse(payload=payload)
        collector = JustTCGCardCollector(api_key='mock-key', session=session)

        cards = collector.collect(
            limit=5,
            set_id='sv-scarlet-violet-151-pokemon',
            number='025/165',
        )

        self.assertEqual([card.card_number for card in cards], ['025/165', '173/165'])
        self.assertTrue(all(card.language == 'UNKNOWN' for card in cards))
        self.assertTrue(all(card.name_ko == '' for card in cards))
        self.assertTrue(all(card.name_en == 'Pikachu' for card in cards))
        self.assertEqual(collector.last_report.excluded_non_card_items, 2)
        session.get.assert_called_once()

        result = import_cards(cards)

        self.assertEqual(result.created, 2)
        self.assertTrue(
            Card.objects.filter(
                source='JUSTTCG',
                external_id='ea180f3a-8c13-59b6-b887-c5cf9f7be4dd',
                card_number='025/165',
                language='UNKNOWN',
            ).exists()
        )
        self.assertTrue(
            Card.objects.filter(
                source='JUSTTCG',
                external_id='4de18046-39c2-572f-8b4c-c8371db5836f',
                card_number='173/165',
                language='UNKNOWN',
            ).exists()
        )

    def test_official_set_and_number_filters_are_forwarded(self):
        session = Mock()
        session.get.return_value = FakeResponse(payload=justtcg_payload())
        collector = JustTCGCardCollector(api_key='mock-key', session=session)

        collector.collect(limit=2, set_id='test-set-pokemon', number='25/100')

        params = session.get.call_args.kwargs['params']
        self.assertEqual(params['set'], 'test-set-pokemon')
        self.assertEqual(params['number'], '25/100')

    def test_collects_pokemon_set_list(self):
        session = Mock()
        session.get.return_value = FakeResponse(
            payload={
                'data': [
                    {
                        'id': 'test-set-pokemon',
                        'name': 'Test Set',
                        'game': 'pokemon',
                        'release_date': '2026-01-01',
                    },
                    {'id': 'other-game', 'name': 'Other', 'game': 'other'},
                ]
            }
        )
        collector = JustTCGCardCollector(api_key='mock-key', session=session)

        sets = collector.collect_sets(query='Test')

        self.assertEqual(len(sets), 1)
        self.assertEqual(sets[0]['id'], 'test-set-pokemon')
        self.assertEqual(session.get.call_args.kwargs['params'], {'game': 'pokemon', 'q': 'Test'})

    def test_justtcg_prices_are_not_saved(self):
        session = Mock()
        session.get.return_value = FakeResponse(payload=justtcg_payload())
        cards = JustTCGCardCollector(api_key='mock-key', session=session).collect(limit=2)

        result = import_cards(cards)

        self.assertEqual(result.created, 2)
        self.assertEqual(
            Card.objects.get(external_id='11111111-1111-5111-8111-111111111111').display_name,
            'Pikachu',
        )
        self.assertEqual(MarketListing.objects.count(), 0)
        self.assertEqual(PriceHistory.objects.count(), 0)

    def test_authentication_failure_is_safe(self):
        session = Mock()
        session.get.return_value = FakeResponse(status_code=401, payload={})

        with self.assertRaisesRegex(JustTCGError, '인증'):
            JustTCGCardCollector(api_key='bad-key', session=session).collect(limit=1)


class JustTCGCommandTests(TestCase):
    @patch('cards.management.commands.import_cards.JustTCGCardCollector')
    def test_dry_run_does_not_save_cards(self, collector_class):
        collector = collector_class.return_value
        collector.collect.return_value = [
            CardData(
                external_id='mock-uuid',
                name_ko='',
                name_en='Pikachu',
                set_name='Test Set',
                card_number='25/100',
                rarity='Common',
                language='KO',
                image_url=None,
                source='JUSTTCG',
            )
        ]
        collector.last_report = JustTCGReport(
            returned_cards=1,
            korean_variant_cards=1,
            english_name_only_cards=1,
            without_image_url=1,
            request_count=1,
            meta={'total': 1, 'limit': 1, 'offset': 0, 'hasMore': False},
        )
        output = StringIO()

        call_command(
            'import_cards',
            source='justtcg',
            limit=1,
            dry_run=True,
            stdout=output,
        )

        self.assertIn('DRY RUN', output.getvalue())
        self.assertEqual(Card.objects.count(), 0)
