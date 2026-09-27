import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured


TRUE_VALUES = {'1', 'true', 'yes', 'on'}
FALSE_VALUES = {'0', 'false', 'no', 'off'}


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().casefold()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return default


def env_list(name, default=()):
    value = os.environ.get(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(',') if item.strip()]


def database_config(database_url, sqlite_path):
    """Use DATABASE_URL when set, otherwise keep local SQLite."""
    if database_url and database_url.strip():
        return dj_database_url.parse(
            database_url,
            conn_max_age=600,
            conn_health_checks=True,
        )
    return {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': sqlite_path,
    }


def secret_key(debug):
    """Allow a local fallback, but never silently use it in production."""
    configured_key = os.environ.get('DJANGO_SECRET_KEY', '').strip()
    if configured_key:
        return configured_key
    if debug:
        return 'django-insecure-local-development-only-change-before-deploy'
    raise ImproperlyConfigured(
        'DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is False.'
    )


def staticfiles_backend(debug):
    if debug:
        return 'django.contrib.staticfiles.storage.StaticFilesStorage'
    return 'whitenoise.storage.CompressedManifestStaticFilesStorage'
