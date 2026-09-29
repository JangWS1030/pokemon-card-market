from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cards.services.collection_orchestrator import disabled_result


SOURCES = (
    ('Pokemon Korea', 'update_pokemon_korea'),
    ('KREAM', 'update_kream'),
    ('Bunjang', 'update_bunjang'),
    ('NAVER CardMVK', 'update_naver_cardmvk'),
)


class Command(BaseCommand):
    help = '국내 collector를 source별로 격리해 순서대로 실행합니다.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        results = []
        failed = 0
        for source, command_name in SOURCES:
            try:
                # 한 source의 DB 변경은 함께 commit/rollback하고, 다음 source와는
                # 분리한다. 현재 비활성 collector는 이 구간에서 write하지 않는다.
                with transaction.atomic():
                    call_command(
                        command_name,
                        dry_run=options['dry_run'],
                        stdout=self.stdout,
                        stderr=self.stderr,
                    )
            except Exception:
                failed += 1
                results.append((source, 'FAILED', 0, 0, 0))
                continue
            result = disabled_result(source)
            results.append((source, result.status, result.created, result.updated, result.skipped))

        self.stdout.write('Korean market collection summary')
        for source, status, _, _, _ in results:
            self.stdout.write(f'{source}: {status}')
        self.stdout.write(f'Total created: {sum(item[2] for item in results)}')
        self.stdout.write(f'Total updated: {sum(item[3] for item in results)}')
        self.stdout.write(f'Total skipped: {sum(item[4] for item in results)}')

        if failed:
            raise CommandError(f'{failed} collector source(s) failed unexpectedly.')
