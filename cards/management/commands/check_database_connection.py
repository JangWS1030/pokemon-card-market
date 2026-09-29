from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = 'credential을 출력하지 않고 DB 연결, backend와 migration 상태를 확인합니다.'

    def add_arguments(self, parser):
        parser.add_argument('--require-postgresql', action='store_true')
        parser.add_argument('--require-migrations', action='store_true')

    def handle(self, *args, **options):
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                result = cursor.fetchone()
        except DatabaseError as error:
            raise CommandError('Database connection: FAILED') from error

        if not result or result[0] != 1:
            raise CommandError('Database connection: FAILED')

        backend_name = {
            'postgresql': 'PostgreSQL',
            'sqlite': 'SQLite',
        }.get(connection.vendor, connection.vendor)
        self.stdout.write(self.style.SUCCESS('Database connection: OK'))
        self.stdout.write(f'Backend: {backend_name}')

        if options['require_postgresql'] and connection.vendor != 'postgresql':
            raise CommandError('PostgreSQL is required for this collector run.')

        try:
            executor = MigrationExecutor(connection)
            pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        except DatabaseError as error:
            raise CommandError('Migration state check: FAILED') from error

        if pending:
            self.stdout.write(f'Migrations: {len(pending)} unapplied')
            if options['require_migrations']:
                raise CommandError('Unapplied migrations prevent collector execution.')
        else:
            self.stdout.write('Migrations: OK')
