from django.core.management.base import BaseCommand


class DisabledSourceCommand(BaseCommand):
    source = ''

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='DB에 쓰지 않는 검증 모드입니다.',
        )

    def handle(self, *args, **options):
        suffix = ' [DRY RUN]' if options['dry_run'] else ''
        self.stdout.write(f'{self.source}: SKIPPED (collector disabled){suffix}')
