import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


ADMIN_ENVIRONMENT_VARIABLES = (
    'DJANGO_ADMIN_USERNAME',
    'DJANGO_ADMIN_EMAIL',
    'DJANGO_ADMIN_PASSWORD',
)


class Command(BaseCommand):
    help = '환경변수가 모두 설정된 경우에만 최초 관리자 계정을 생성합니다.'

    def handle(self, *args, **options):
        values = {
            name: os.environ.get(name)
            for name in ADMIN_ENVIRONMENT_VARIABLES
        }
        if any(value is None or not value.strip() for value in values.values()):
            self.stdout.write(
                self.style.WARNING(
                    'Admin environment variables are not configured; skipping.'
                )
            )
            return

        username = values['DJANGO_ADMIN_USERNAME'].strip()
        email = values['DJANGO_ADMIN_EMAIL'].strip()
        password = values['DJANGO_ADMIN_PASSWORD']
        user_model = get_user_model()
        existing_user = user_model._default_manager.filter(username=username).first()

        if existing_user is not None:
            if existing_user.is_staff and existing_user.is_superuser:
                message = 'Admin user already exists; skipping.'
            else:
                message = 'Username already belongs to a non-admin user; skipping.'
            self.stdout.write(self.style.WARNING(message))
            return

        user_model._default_manager.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        self.stdout.write(self.style.SUCCESS('Admin user created successfully.'))
