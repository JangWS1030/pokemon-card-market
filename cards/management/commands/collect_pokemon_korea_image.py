from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Pokemon Korea 자동 공개 페이지 수집은 HTTP 410 재현으로 비활성화되어 있습니다.'

    def add_arguments(self, parser):
        parser.add_argument('--card-id', type=int)
        parser.add_argument('--url')
        parser.add_argument('--check-image', action='store_true')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--write', action='store_true')

    def handle(self, *args, **options):
        self.stdout.write(
            'SKIPPED: Pokemon Korea public page returned HTTP 410 in the verified '
            'user environment. Automatic collection is disabled.'
        )
