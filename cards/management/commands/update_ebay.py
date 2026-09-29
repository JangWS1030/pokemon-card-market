from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = '명시한 Card 한 장에 대해서만 기존 eBay update_prices 흐름을 실행합니다.'

    def add_arguments(self, parser):
        parser.add_argument('--card-id', type=int)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        card_id = options['card_id']
        if card_id is None:
            self.stdout.write('eBay: SKIPPED (explicit --card-id required)')
            return

        call_command(
            'update_prices',
            card_id=card_id,
            limit=1,
            dry_run=options['dry_run'],
            stdout=self.stdout,
            stderr=self.stderr,
        )
