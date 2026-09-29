import re
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlparse

from django.utils import timezone

from cards.collectors import InvalidResponseError, MarketData, MissingFieldError, RequestSafetyPolicy
from cards.collectors.public_http import PublicHttpClient
from cards.services.normalization import parse_krw_price

from .fixture_support import _http_url


PUBLIC_HOSTS = {'app.break.market'}
IMAGE_HOSTS = {'d2ot1525u67uvs.cloudfront.net'}
PRODUCT_PATH_PATTERN = re.compile(r'^/products/(?P<external_id>\d+)(?:/.*)?$')
PRICE_PATTERN = re.compile(r'가격\s+([\d,]+원)\s+\((현재 입찰가|즉시 구매가)\)')


class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values = {}

    def handle_starttag(self, tag, attrs):
        if tag != 'meta':
            return
        attributes = dict(attrs)
        key = attributes.get('property') or attributes.get('name')
        if key and attributes.get('content'):
            self.values[key.casefold()] = attributes['content'].strip()


class BreakMarketCollector:
    """One public BREAK product URL per invocation; no search or pagination."""

    SOURCE = 'BREAK'
    HTTP_ENABLED = True
    REQUEST_POLICY = RequestSafetyPolicy(max_items=1, request_budget=1, retry_limit=0)

    def __init__(self, client=None):
        self.client = client or PublicHttpClient(PUBLIC_HOSTS, policy=self.REQUEST_POLICY)

    @property
    def request_count(self):
        return self.client.request_count

    def collect_url(self, url):
        parsed_url = urlparse(url)
        path_match = PRODUCT_PATH_PATTERN.fullmatch(parsed_url.path)
        if parsed_url.hostname not in PUBLIC_HOSTS or not path_match:
            raise InvalidResponseError('BREAK 공개 상품 URL만 허용합니다.')

        response = self.client.get_html(url)
        parser = _MetaParser()
        parser.feed(response.text)
        description = parser.values.get('og:description', '')
        price_match = PRICE_PATTERN.search(description)
        if not price_match:
            raise InvalidResponseError('BREAK 공개 페이지에서 명시적인 현재 가격을 확인할 수 없습니다.')

        raw_title = parser.values.get('og:title', '')
        title = _title_without_seller(raw_title)
        if price_match.group(2) == '현재 입찰가':
            title = f'진행 중 경매 · {title}'

        image_url = _allowed_image_url(parser.values.get('og:image', ''))
        return MarketData(
            external_id=path_match.group('external_id'),
            title=title,
            price=parse_krw_price(price_match.group(1)),
            currency='KRW',
            url=response.url,
            image_url=image_url,
            listing_type='CURRENT_LISTING',
            occurred_at=None,
            collected_at=timezone.now(),
            source=self.SOURCE,
        )

    @classmethod
    def normalize(cls, item):
        """Pure fixture normalizer, including only explicitly final auction results."""
        if not isinstance(item, dict):
            raise InvalidResponseError('BREAK fixture 형식이 올바르지 않습니다.')
        data_type = item.get('data_type')
        if data_type == 'CURRENT_LISTING':
            listing_type = 'CURRENT_LISTING'
            occurred_at = None
        elif data_type == 'AUCTION_RESULT' and item.get('final_result_confirmed') is True:
            listing_type = 'AUCTION_RESULT'
            occurred_at = item.get('occurred_at')
            if occurred_at is None:
                raise InvalidResponseError('BREAK 종료 경매에는 확인된 종료 시간이 필요합니다.')
        else:
            raise InvalidResponseError('BREAK는 현재 매물 또는 확인된 최종 경매 결과만 허용합니다.')

        required = ('external_id', 'title', 'price', 'url', 'collected_at')
        missing = [field for field in required if item.get(field) in (None, '')]
        if missing:
            raise MissingFieldError(f"BREAK fixture 필수 필드가 없습니다: {', '.join(missing)}")
        if not isinstance(item['collected_at'], datetime):
            raise InvalidResponseError('BREAK collected_at은 datetime이어야 합니다.')
        if occurred_at is not None and not isinstance(occurred_at, datetime):
            raise InvalidResponseError('BREAK occurred_at은 datetime이어야 합니다.')
        return MarketData(
            external_id=str(item['external_id']).strip(),
            title=str(item['title']).strip(),
            price=parse_krw_price(item['price']),
            currency='KRW',
            url=_http_url(item['url'], required=True),
            image_url=_allowed_image_url(item.get('image_url', '')),
            listing_type=listing_type,
            occurred_at=occurred_at,
            collected_at=item['collected_at'],
            source=cls.SOURCE,
        )


def _title_without_seller(value):
    title = value.split(' · ', 1)[0].strip()
    title = re.sub(
        r'(?:\s+[\d,]+원)?\s+(?:경매|즉시 구매)(?:\s+[\d,]+원)?$',
        '',
        title,
    ).strip()
    if not title:
        raise MissingFieldError('BREAK 공개 페이지의 상품명이 비어 있습니다.')
    return title


def _allowed_image_url(value):
    if not value:
        return ''
    parsed = urlparse(value)
    if (
        parsed.scheme == 'https'
        and parsed.hostname in IMAGE_HOSTS
        and not parsed.username
        and not parsed.password
    ):
        return value
    return ''
