import os

from django.core.management.base import BaseCommand, CommandError

from cards.collectors.card_data import JustTCGCardCollector, JustTCGError
from cards.services.card_importer import import_cards


class Command(BaseCommand):
    help = '환경변수로 범위를 제한해 JustTCG Card를 한 번만 요청하고 저장합니다.'

    def handle(self, *args, **options):
        set_id = os.environ.get('JUSTTCG_IMPORT_SET', '').strip()
        number = os.environ.get('JUSTTCG_IMPORT_NUMBER', '').strip()
        if not set_id or not number:
            self.stdout.write(
                self.style.WARNING(
                    'JustTCG import filters are not fully configured; skipping.'
                )
            )
            return

        raw_limit = os.environ.get('JUSTTCG_IMPORT_LIMIT', '').strip() or '5'
        try:
            limit = int(raw_limit)
        except ValueError:
            self.stdout.write(
                self.style.WARNING('JustTCG import limit is invalid; skipping.')
            )
            return
        if not 1 <= limit <= 10:
            self.stdout.write(
                self.style.WARNING('JustTCG import limit must be between 1 and 10; skipping.')
            )
            return

        collector = JustTCGCardCollector()
        try:
            cards = collector.collect(
                limit=limit,
                set_id=set_id,
                number=number,
            )
        except (JustTCGError, ValueError) as error:
            raise CommandError(str(error)) from error

        result = import_cards(cards)
        self.stdout.write(
            self.style.SUCCESS(
                'JustTCG one-time import completed: '
                f'returned {collector.last_report.returned_cards}, '
                f'eligible {len(cards)}, created {result.created}, '
                f'updated {result.updated}, skipped {result.skipped}, errors {result.errors}.'
            )
        )
