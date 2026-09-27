import os
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase


ADMIN_ENV = {
    'DJANGO_ADMIN_USERNAME': 'test-bootstrap-admin',
    'DJANGO_ADMIN_EMAIL': 'bootstrap-admin@example.test',
    'DJANGO_ADMIN_PASSWORD': 'test-only-password-4827',
}


class EnsureAdminCommandTests(TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_environment_variables_skip_creation(self):
        output = StringIO()

        call_command('ensure_admin', stdout=output)

        self.assertEqual(get_user_model().objects.count(), 0)
        self.assertIn('not configured; skipping', output.getvalue())

    @patch.dict(
        os.environ,
        {'DJANGO_ADMIN_USERNAME': ADMIN_ENV['DJANGO_ADMIN_USERNAME']},
        clear=True,
    )
    def test_partial_environment_variables_skip_creation(self):
        call_command('ensure_admin', stdout=StringIO())

        self.assertEqual(get_user_model().objects.count(), 0)

    @patch.dict(os.environ, ADMIN_ENV, clear=True)
    def test_complete_environment_creates_hashed_superuser(self):
        output = StringIO()

        call_command('ensure_admin', stdout=output)

        user = get_user_model().objects.get(username=ADMIN_ENV['DJANGO_ADMIN_USERNAME'])
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertNotEqual(user.password, ADMIN_ENV['DJANGO_ADMIN_PASSWORD'])
        self.assertTrue(user.check_password(ADMIN_ENV['DJANGO_ADMIN_PASSWORD']))
        for value in ADMIN_ENV.values():
            self.assertNotIn(value, output.getvalue())

    def test_repeated_command_does_not_duplicate_or_change_password(self):
        first_password = 'first-test-password-1942'
        second_password = 'second-test-password-7351'
        first_environment = {**ADMIN_ENV, 'DJANGO_ADMIN_PASSWORD': first_password}
        second_environment = {**ADMIN_ENV, 'DJANGO_ADMIN_PASSWORD': second_password}

        with patch.dict(os.environ, first_environment, clear=True):
            call_command('ensure_admin', stdout=StringIO())
        with patch.dict(os.environ, second_environment, clear=True):
            call_command('ensure_admin', stdout=StringIO())

        user = get_user_model().objects.get(username=ADMIN_ENV['DJANGO_ADMIN_USERNAME'])
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertTrue(user.check_password(first_password))
        self.assertFalse(user.check_password(second_password))

    @patch.dict(os.environ, ADMIN_ENV, clear=True)
    def test_existing_non_admin_is_not_promoted_or_modified(self):
        original_password = 'original-test-password-9513'
        user = get_user_model().objects.create_user(
            username=ADMIN_ENV['DJANGO_ADMIN_USERNAME'],
            email='existing-user@example.test',
            password=original_password,
        )
        original_email = user.email

        call_command('ensure_admin', stdout=StringIO())

        user.refresh_from_db()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.email, original_email)
        self.assertTrue(user.check_password(original_password))
        self.assertFalse(user.check_password(ADMIN_ENV['DJANGO_ADMIN_PASSWORD']))
