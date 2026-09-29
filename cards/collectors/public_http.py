from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests

from cards.collectors import (
    AuthenticationError,
    CollectorTimeoutError,
    ExternalAPIError,
    InvalidResponseError,
    RateLimitError,
    RequestSafetyPolicy,
)


DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
USER_AGENT = 'PokemonCardMarketPersonal/1.0 (low-volume public-page collector)'
CHALLENGE_MARKERS = (
    'captcha',
    'cf-chl-',
    'cloudflare challenge',
    '<title>just a moment',
    'verify you are human',
    '로그인이 필요합니다',
    '회원 전용',
)


@dataclass(frozen=True, slots=True)
class PublicHttpResponse:
    url: str
    content: bytes
    content_type: str

    @property
    def text(self):
        return self.content.decode('utf-8', errors='replace')


class PublicHttpClient:
    """Small, transparent HTTP client for explicitly approved public pages."""

    def __init__(
        self,
        allowed_hosts,
        policy=None,
        max_response_bytes=DEFAULT_MAX_RESPONSE_BYTES,
        max_redirects=2,
        session=None,
    ):
        self.allowed_hosts = {host.casefold() for host in allowed_hosts}
        self.policy = policy or RequestSafetyPolicy()
        self.max_response_bytes = max_response_bytes
        self.max_redirects = max_redirects
        self.session = session or requests.Session()
        self.request_count = 0

    def get_html(self, url):
        response = self._request('GET', url, expected_prefix='text/html')
        lowered = response.text.casefold()
        if any(marker in lowered for marker in CHALLENGE_MARKERS):
            raise ExternalAPIError('Public page returned a login or anti-bot challenge.')
        return response

    def head_image(self, url):
        return self._request('HEAD', url, expected_prefix='image/')

    def _request(self, method, url, expected_prefix):
        current_url = url
        for redirect_count in range(self.max_redirects + 1):
            self._validate_url(current_url)
            if self.request_count >= self.policy.request_budget:
                raise ExternalAPIError('Public collector request budget was exhausted.')
            self.request_count += 1
            try:
                response = self.session.request(
                    method,
                    current_url,
                    headers={'User-Agent': USER_AGENT, 'Accept': f'{expected_prefix}*'},
                    timeout=self.policy.timeout_seconds,
                    allow_redirects=False,
                    stream=True,
                )
            except requests.Timeout as error:
                raise CollectorTimeoutError('Public page request timed out.') from error
            except requests.RequestException as error:
                raise ExternalAPIError('Public page request failed.') from error

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get('Location', '')
                if not location or redirect_count >= self.max_redirects:
                    raise ExternalAPIError('Public page redirect limit was exceeded.')
                current_url = urljoin(current_url, location)
                self._validate_url(current_url)
                continue

            self._raise_for_status(response.status_code)
            content_type = response.headers.get('Content-Type', '').split(';', 1)[0].strip().casefold()
            if not content_type.startswith(expected_prefix):
                raise InvalidResponseError('Public page returned an unexpected content type.')

            content_length = response.headers.get('Content-Length')
            if content_length:
                try:
                    if int(content_length) > self.max_response_bytes:
                        raise InvalidResponseError('Public response exceeded the size limit.')
                except ValueError:
                    raise InvalidResponseError('Public response size header was invalid.')

            body = bytearray()
            if method != 'HEAD':
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    body.extend(chunk)
                    if len(body) > self.max_response_bytes:
                        raise InvalidResponseError('Public response exceeded the size limit.')
            return PublicHttpResponse(current_url, bytes(body), content_type)

        raise ExternalAPIError('Public page redirect limit was exceeded.')

    def _validate_url(self, url):
        parsed = urlparse(url)
        if (
            parsed.scheme != 'https'
            or not parsed.hostname
            or parsed.hostname.casefold() not in self.allowed_hosts
            or parsed.username
            or parsed.password
        ):
            raise InvalidResponseError('Public URL host or scheme is not allowed.')

    @staticmethod
    def _raise_for_status(status_code):
        if status_code == 401:
            raise AuthenticationError('Public page requires authentication.')
        if status_code == 403:
            raise ExternalAPIError('Public page access was forbidden; collection stopped.')
        if status_code == 429:
            raise RateLimitError('Public page rate limit was reached; collection stopped.')
        if status_code >= 400:
            raise ExternalAPIError(f'Public page request failed with HTTP {status_code}.')
