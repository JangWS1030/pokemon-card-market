import os
import time
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import requests
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
)


class EbayMarketCollector:
    TOKEN_URL = 'https://api.ebay.com/identity/v1/oauth2/token'
    SEARCH_URL = 'https://api.ebay.com/buy/browse/v1/item_summary/search'
    OAUTH_SCOPE = 'https://api.ebay.com/oauth/api_scope'
    MARKETPLACE_ID = 'EBAY_US'

    def __init__(self, client_id=None, client_secret=None, session=None, timeout=10):
        self.client_id = client_id or os.environ.get('EBAY_CLIENT_ID')
        self.client_secret = client_secret or os.environ.get('EBAY_CLIENT_SECRET')
        self.session = session or requests.Session()
        self.timeout = timeout
        self._access_token = None
        self._token_expires_at = 0.0

    @property
    def is_configured(self):
        return bool(self.client_id and self.client_secret)

    def get_access_token(self):
        if not self.is_configured:
            raise MissingCredentialsError(
                'eBay 개발자 인증정보가 없습니다. EBAY_CLIENT_ID와 '
                'EBAY_CLIENT_SECRET을 설정해 주세요.'
            )

        if self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token

        try:
            response = self.session.post(
                self.TOKEN_URL,
                auth=(self.client_id, self.client_secret),
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                data={
                    'grant_type': 'client_credentials',
                    'scope': self.OAUTH_SCOPE,
                },
                timeout=self.timeout,
            )
        except requests.Timeout as error:
            raise CollectorTimeoutError('eBay OAuth 요청 시간이 초과되었습니다.') from error
        except requests.RequestException as error:
            raise ExternalAPIError('eBay OAuth 요청에 실패했습니다.') from error

        self._raise_for_status(response, authentication_request=True)
        payload = self._read_json(response, 'eBay OAuth 응답이 올바른 JSON이 아닙니다.')
        access_token = payload.get('access_token')
        if not access_token:
            raise InvalidResponseError('eBay OAuth 응답에 access_token이 없습니다.')

        expires_in = payload.get('expires_in', 7200)
        try:
            expires_in = max(int(expires_in), 60)
        except (TypeError, ValueError):
            expires_in = 7200

        self._access_token = access_token
        self._token_expires_at = time.monotonic() + expires_in - 30
        return access_token

    def collect(self, query, limit=20):
        query = query.strip() if isinstance(query, str) else ''
        if not query:
            raise ValueError('eBay 검색어가 비어 있습니다.')
        if not 1 <= limit <= 200:
            raise ValueError('eBay 검색 결과 수는 1~200 사이여야 합니다.')

        token = self.get_access_token()
        try:
            response = self.session.get(
                self.SEARCH_URL,
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-EBAY-C-MARKETPLACE-ID': self.MARKETPLACE_ID,
                },
                params={'q': query, 'limit': limit},
                timeout=self.timeout,
            )
        except requests.Timeout as error:
            raise CollectorTimeoutError('eBay Browse API 요청 시간이 초과되었습니다.') from error
        except requests.RequestException as error:
            raise ExternalAPIError('eBay Browse API 요청에 실패했습니다.') from error

        self._raise_for_status(response)
        payload = self._read_json(response, 'eBay Browse API 응답이 올바른 JSON이 아닙니다.')
        item_summaries = payload.get('itemSummaries', [])
        if not isinstance(item_summaries, list):
            raise InvalidResponseError('eBay Browse API의 itemSummaries 형식이 올바르지 않습니다.')

        return [self.normalize(item) for item in item_summaries]

    def normalize(self, item):
        if not isinstance(item, dict):
            raise InvalidResponseError('eBay 상품 데이터 형식이 올바르지 않습니다.')

        price_data = item.get('price')
        required_values = {
            'itemId': item.get('itemId'),
            'title': item.get('title'),
            'itemWebUrl': item.get('itemWebUrl'),
            'price.value': price_data.get('value') if isinstance(price_data, dict) else None,
            'price.currency': price_data.get('currency') if isinstance(price_data, dict) else None,
        }
        missing_fields = [name for name, value in required_values.items() if value in (None, '')]
        if missing_fields:
            raise MissingFieldError(
                f"eBay 상품 응답에 필수 필드가 없습니다: {', '.join(missing_fields)}"
            )

        try:
            price = Decimal(str(required_values['price.value']))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise InvalidResponseError('eBay 상품 가격을 숫자로 변환할 수 없습니다.') from error
        if price <= 0:
            raise InvalidResponseError('eBay 상품 가격은 0보다 커야 합니다.')

        currency = str(required_values['price.currency']).upper()
        if len(currency) != 3:
            raise InvalidResponseError('eBay 상품 통화 코드는 3자리여야 합니다.')

        item_url = str(required_values['itemWebUrl'])
        if urlparse(item_url).scheme not in ('http', 'https'):
            raise InvalidResponseError('eBay 상품 URL 형식이 올바르지 않습니다.')

        image_url = ''
        image_data = item.get('image')
        if isinstance(image_data, dict):
            candidate = image_data.get('imageUrl')
            if isinstance(candidate, str) and urlparse(candidate).scheme in ('http', 'https'):
                image_url = candidate

        return MarketData(
            external_id=str(required_values['itemId']),
            title=str(required_values['title']),
            price=price,
            currency=currency,
            url=item_url,
            collected_at=timezone.now(),
            source='EBAY',
            image_url=image_url,
        )

    @staticmethod
    def _read_json(response, message):
        try:
            payload = response.json()
        except ValueError as error:
            raise InvalidResponseError(message) from error
        if not isinstance(payload, dict):
            raise InvalidResponseError(message)
        return payload

    def _raise_for_status(self, response, authentication_request=False):
        if 200 <= response.status_code < 300:
            return
        if authentication_request:
            raise AuthenticationError(self._oauth_failure_message(response))
        if response.status_code in (401, 403):
            raise AuthenticationError('eBay API 인증에 실패했습니다.')
        if response.status_code == 429:
            raise RateLimitError('eBay API 호출 한도를 초과했습니다.')
        raise ExternalAPIError(f'eBay API가 HTTP {response.status_code} 오류를 반환했습니다.')

    def _oauth_failure_message(self, response):
        try:
            payload = response.json()
        except (TypeError, ValueError):
            payload = None

        error_name = 'unknown'
        description = 'unavailable (non-JSON response)'
        if isinstance(payload, dict):
            error_name = self._safe_diagnostic_value(
                payload.get('error') or payload.get('code') or payload.get('errorId'),
                fallback='unknown',
            )
            description = self._safe_diagnostic_value(
                payload.get('error_description') or payload.get('message'),
                fallback='no safe error description returned',
            )

        return (
            f'eBay OAuth failed: status={response.status_code}, '
            f'error={error_name}, description={description}'
        )

    def _safe_diagnostic_value(self, value, fallback):
        if not isinstance(value, (str, int, float)):
            return fallback

        text = ' '.join(str(value).split())[:200]
        if not text:
            return fallback

        sensitive_values = (self.client_id, self.client_secret, self._access_token)
        if any(secret and str(secret) in text for secret in sensitive_values):
            return '[redacted]'

        lowered = text.casefold()
        sensitive_markers = (
            'authorization:',
            'basic ',
            'bearer ',
            'access_token',
            'refresh_token',
            'client_secret',
        )
        if any(marker in lowered for marker in sensitive_markers):
            return '[redacted]'
        return text
