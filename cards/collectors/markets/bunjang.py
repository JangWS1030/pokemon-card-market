import base64
import hashlib
import hmac
import json
import time
import uuid
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.utils import timezone

from cards.collectors import (
    AuthenticationError,
    CollectorTimeoutError,
    ExternalAPIError,
    InvalidResponseError,
    MarketData,
    MissingCredentialsError,
    MissingFieldError,
    RateLimitError,
    RequestSafetyPolicy,
)
from cards.services.normalization import parse_krw_price


class BunjangMarketCollector:
    """Official Bunjang Open API product search with one request and no pagination."""

    SOURCE = 'BUNJANG'
    BASE_URL = 'https://openapi.bunjang.co.kr'
    SEARCH_PATH = '/api/v1/products'
    PUBLIC_PRODUCT_BASE_URL = 'https://m.bunjang.co.kr/products'
    IMAGE_HOSTS = {'media.bunjang.co.kr'}
    REQUEST_POLICY = RequestSafetyPolicy(max_items=5, request_budget=1, retry_limit=0)
    MAX_RESPONSE_BYTES = 2 * 1024 * 1024

    def __init__(self, access_key=None, secret_key=None, session=None, now=None):
        self.access_key = (
            settings.BUNJANG_ACCESS_KEY if access_key is None else access_key
        ).strip()
        self.secret_key = (
            settings.BUNJANG_SECRET_KEY if secret_key is None else secret_key
        ).strip()
        self.session = session or requests.Session()
        self.now = now or time.time
        self.request_count = 0

    @property
    def is_configured(self):
        return bool(self.access_key and self.secret_key)

    def build_jwt(self, method='GET'):
        if not self.is_configured:
            raise MissingCredentialsError('Bunjang Open API credentials are not configured.')
        try:
            signing_key = base64.b64decode(self.secret_key, validate=True)
        except (ValueError, TypeError) as error:
            raise AuthenticationError('Bunjang secret key is not valid Base64.') from error
        if not signing_key:
            raise AuthenticationError('Bunjang secret key is empty after Base64 decoding.')

        payload = {'iat': int(self.now()), 'accessKey': self.access_key}
        if method.upper() in {'POST', 'PUT', 'DELETE'}:
            payload['nonce'] = str(uuid.uuid4())
        header = {'alg': 'HS256', 'typ': 'JWT'}
        signing_input = b'.'.join((_jwt_segment(header), _jwt_segment(payload)))
        signature = hmac.new(signing_key, signing_input, hashlib.sha256).digest()
        return b'.'.join((signing_input, _base64url(signature))).decode('ascii')

    def collect(self, query, limit=3):
        if not isinstance(query, str) or not query.strip():
            raise ValueError('Bunjang search query is required.')
        if not 1 <= limit <= self.REQUEST_POLICY.max_items:
            raise ValueError('Bunjang result limit must be between 1 and 5.')
        if not self.is_configured:
            raise MissingCredentialsError('Bunjang Open API credentials are not configured.')
        if self.request_count >= self.REQUEST_POLICY.request_budget:
            raise ExternalAPIError('Bunjang request budget was exhausted.')

        self.request_count += 1
        try:
            response = self.session.request(
                'GET',
                f'{self.BASE_URL}{self.SEARCH_PATH}',
                params={'q': query.strip(), 'size': limit},
                headers={
                    'Authorization': f'Bearer {self.build_jwt("GET")}',
                    'Accept': 'application/json',
                    'User-Agent': 'PokemonCardMarketPersonal/1.0',
                },
                timeout=self.REQUEST_POLICY.timeout_seconds,
                allow_redirects=False,
                stream=True,
            )
        except requests.Timeout as error:
            raise CollectorTimeoutError('Bunjang product search timed out.') from error
        except requests.RequestException as error:
            raise ExternalAPIError('Bunjang product search failed.') from error

        if response.status_code == 401:
            raise AuthenticationError('Bunjang Open API authentication failed.')
        if response.status_code == 429:
            raise RateLimitError('Bunjang Open API rate limit was reached.')
        if 300 <= response.status_code < 400:
            raise ExternalAPIError('Bunjang Open API returned an unexpected redirect.')
        if response.status_code >= 400:
            raise ExternalAPIError(f'Bunjang product search failed with HTTP {response.status_code}.')
        content_type = response.headers.get('Content-Type', '').split(';', 1)[0].casefold()
        if content_type != 'application/json':
            raise InvalidResponseError('Bunjang product search returned non-JSON content.')

        body = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if chunk:
                body.extend(chunk)
                if len(body) > self.MAX_RESPONSE_BYTES:
                    raise InvalidResponseError('Bunjang response exceeded the size limit.')
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InvalidResponseError('Bunjang product search returned invalid JSON.') from error
        items = payload.get('data') if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise InvalidResponseError('Bunjang product search response has no data list.')
        return [self.normalize(item) for item in items[:limit]]

    @classmethod
    def normalize(cls, item):
        if not isinstance(item, dict):
            raise InvalidResponseError('Bunjang product data must be an object.')
        required = ('pid', 'name', 'price', 'saleStatus')
        missing = [field for field in required if item.get(field) in (None, '')]
        if missing:
            raise MissingFieldError(f"Bunjang product fields are missing: {', '.join(missing)}")
        if item['saleStatus'] != 'SELLING':
            raise InvalidResponseError('Only Bunjang SELLING products are current listings.')

        external_id = str(item['pid']).strip()
        title = str(item['name']).strip()
        if not external_id.isdigit() or not title:
            raise InvalidResponseError('Bunjang product identity is invalid.')

        return MarketData(
            external_id=external_id,
            title=title,
            price=parse_krw_price(item['price']),
            currency='KRW',
            url=f'{cls.PUBLIC_PRODUCT_BASE_URL}/{external_id}',
            image_url=cls._image_url(item),
            listing_type='CURRENT_LISTING',
            occurred_at=None,
            collected_at=timezone.now(),
            source=cls.SOURCE,
        )

    @classmethod
    def _image_url(cls, item):
        template = item.get('imageUrlTemplate')
        image_count = item.get('imageCount')
        if not isinstance(template, str) or not isinstance(image_count, int) or image_count < 1:
            return ''
        image_url = template.replace('{cnt}', '1')
        parsed = urlparse(image_url)
        if (
            parsed.scheme == 'https'
            and parsed.hostname in cls.IMAGE_HOSTS
            and not parsed.username
            and not parsed.password
        ):
            return image_url
        return ''


def _jwt_segment(value):
    encoded = json.dumps(value, separators=(',', ':'), ensure_ascii=True).encode('utf-8')
    return _base64url(encoded)


def _base64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=')
