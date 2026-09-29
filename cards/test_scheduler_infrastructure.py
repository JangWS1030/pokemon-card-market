from datetime import timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from cards.collectors import MarketData, RequestSafetyPolicy
from cards.models import (
    Card,
    Condition,
    ListingType,
    MarketListing,
    MarketRegion,
    MarketSource,
    PriceHistory,
)
from cards.services.condition_classifier import ConditionResult
from cards.services.market_importer import save_market_listing
from cards.services.price_calculator import calculate_price_groups
from cards.services.price_history import DUPLICATE_WINDOW, save_price_histories
from config.env import database_config


class DatabaseConnectionCommandTests(TestCase):
    def test_local_sqlite_connection_and_migrations_are_reported_safely(self):
        output = StringIO()

        call_command(
            'check_database_connection',
            require_migrations=True,
            stdout=output,
        )

        text = output.getvalue()
        self.assertIn('Database connection: OK', text)
        self.assertIn('Backend: SQLite', text)
        self.assertIn('Migrations: OK', text)
        self.assertNotIn(str(settings.DATABASES['default']['NAME']), text)

    def test_postgresql_requirement_rejects_sqlite_without_credentials(self):
        output = StringIO()

        with self.assertRaisesMessage(CommandError, 'PostgreSQL is required'):
            call_command(
                'check_database_connection',
                require_postgresql=True,
                stdout=output,
            )

        text = output.getvalue()
        self.assertNotIn('DATABASE_URL', text)
        self.assertNotIn('password', text.casefold())

    def test_external_postgresql_sslmode_is_preserved(self):
        config = database_config(
            'postgresql://example.invalid/cards?sslmode=require',
            Path('unused.sqlite3'),
        )

        self.assertEqual(config['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(config['OPTIONS']['sslmode'], 'require')


class DisabledCollectorCommandTests(TestCase):
    commands = (
        'update_pokemon_korea',
        'update_kream',
        'update_bunjang',
        'update_naver_cardmvk',
    )

    def test_disabled_source_commands_skip_without_writes(self):
        before = self._counts()

        for command_name in self.commands:
            with self.subTest(command=command_name):
                output = StringIO()
                call_command(command_name, dry_run=True, stdout=output)
                self.assertIn('SKIPPED (collector disabled)', output.getvalue())

        self.assertEqual(self._counts(), before)

    @patch('cards.management.commands.update_ebay.call_command')
    def test_update_ebay_without_explicit_card_skips(self, delegated_command):
        output = StringIO()

        call_command('update_ebay', dry_run=True, stdout=output)

        self.assertIn('SKIPPED', output.getvalue())
        delegated_command.assert_not_called()

    def test_korean_orchestration_reports_expected_skips(self):
        output = StringIO()

        call_command('update_korean_market', dry_run=True, stdout=output)

        text = output.getvalue()
        for source in ('Pokemon Korea', 'KREAM', 'Bunjang', 'NAVER CardMVK'):
            self.assertIn(f'{source}: SKIPPED', text)
        self.assertIn('Total created: 0', text)
        self.assertIn('Total updated: 0', text)
        self.assertIn('Total skipped: 4', text)
        self.assertEqual(self._counts(), (0, 0, 0, 0))

    @patch('cards.management.commands.update_korean_market.call_command')
    def test_unexpected_source_failure_does_not_stop_later_sources(self, source_command):
        calls = []

        def run(command_name, **kwargs):
            calls.append(command_name)
            if command_name == 'update_kream':
                raise RuntimeError('unexpected test failure')

        source_command.side_effect = run
        output = StringIO()

        with self.assertRaisesMessage(CommandError, '1 collector source'):
            call_command('update_korean_market', dry_run=True, stdout=output)

        self.assertEqual(calls, list(self.commands))
        self.assertIn('KREAM: FAILED', output.getvalue())
        self.assertIn('NAVER CardMVK: SKIPPED', output.getvalue())

    @staticmethod
    def _counts():
        return (
            Card.objects.count(),
            MarketSource.objects.count(),
            MarketListing.objects.count(),
            PriceHistory.objects.count(),
        )


class SchedulerDataSafetyTests(TestCase):
    def setUp(self):
        self.card = Card.objects.create(
            source='TEST',
            external_id='scheduler-card',
            name_ko='피카츄',
            set_name='포켓몬 카드 151',
            card_number='025/165',
            language='KO',
        )
        self.source = MarketSource.objects.create(
            code='TEST_MARKET',
            name='Test Market',
            market_region=MarketRegion.KR,
        )

    def test_listing_upsert_keeps_one_row_and_updates_listing_type(self):
        now = timezone.now()
        first = self._market_data(ListingType.CURRENT_LISTING, now)
        second = self._market_data(ListingType.SOLD, now + timedelta(minutes=1))

        created = save_market_listing(
            first,
            self.card,
            self.source,
            ConditionResult(condition=Condition.RAW),
        )
        updated = save_market_listing(
            second,
            self.card,
            self.source,
            ConditionResult(condition=Condition.RAW),
        )

        self.assertTrue(created.created)
        self.assertFalse(updated.created)
        self.assertEqual(MarketListing.objects.count(), 1)
        self.assertEqual(MarketListing.objects.get().listing_type, ListingType.SOLD)

    def test_identical_price_snapshot_within_window_is_reused(self):
        calculated_at = timezone.now()
        calculations = calculate_price_groups([self._listing(ListingType.SOLD)])

        first = save_price_histories(calculations, calculated_at=calculated_at)
        second = save_price_histories(
            calculations,
            calculated_at=calculated_at + timedelta(minutes=1),
        )

        self.assertEqual(PriceHistory.objects.count(), 1)
        self.assertEqual(first[0].pk, second[0].pk)
        self.assertEqual(PriceHistory.objects.get().listing_type, ListingType.SOLD)

    def test_identical_price_snapshot_after_window_creates_history(self):
        calculated_at = timezone.now()
        calculations = calculate_price_groups([self._listing(ListingType.SOLD)])

        save_price_histories(calculations, calculated_at=calculated_at)
        save_price_histories(
            calculations,
            calculated_at=calculated_at + DUPLICATE_WINDOW + timedelta(seconds=1),
        )

        self.assertEqual(PriceHistory.objects.count(), 2)

    def test_request_safety_defaults_are_bounded(self):
        policy = RequestSafetyPolicy()

        self.assertEqual(policy.timeout_seconds, 10)
        self.assertEqual(policy.max_pages, 1)
        self.assertEqual(policy.max_items, 20)
        self.assertEqual(policy.retry_limit, 0)
        self.assertEqual(policy.request_budget, 1)

    def _market_data(self, listing_type, occurred_at):
        return MarketData(
            external_id='same-listing',
            title='피카츄 025/165',
            price=Decimal('12000'),
            currency='KRW',
            url='https://example.com/listing/1',
            collected_at=occurred_at,
            source='TEST_MARKET',
            listing_type=listing_type,
            occurred_at=occurred_at,
        )

    def _listing(self, listing_type):
        return SimpleNamespace(
            card_id=self.card.pk,
            condition=Condition.RAW,
            grading_score=None,
            currency='KRW',
            listing_type=listing_type,
            price=Decimal('12000'),
            is_active=True,
        )


class WorkflowDefinitionTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.workflow = (
            Path(settings.BASE_DIR) / '.github' / 'workflows' / 'collect-market.yml'
        ).read_text(encoding='utf-8')

    def test_workflow_is_manual_only_and_bounded(self):
        self.assertIn('workflow_dispatch:', self.workflow)
        self.assertNotIn('schedule:', self.workflow)
        self.assertIn('contents: read', self.workflow)
        self.assertIn('group: market-collector', self.workflow)
        self.assertIn('cancel-in-progress: false', self.workflow)
        self.assertIn('timeout-minutes: 10', self.workflow)
        self.assertIn('python-version: "3.13"', self.workflow)

    def test_workflow_uses_only_database_secret_and_safe_commands(self):
        self.assertIn('${{ secrets.DATABASE_URL }}', self.workflow)
        self.assertIn(
            'check_database_connection --require-postgresql --require-migrations',
            self.workflow,
        )
        self.assertIn('update_korean_market --dry-run', self.workflow)
        for forbidden in (
            'manage.py migrate',
            'manage.py makemigrations',
            'manage.py flush',
            'seed_demo_data',
            'clear_demo_data',
            'EBAY_CLIENT_ID',
            'JUSTTCG_API_KEY',
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.workflow)
