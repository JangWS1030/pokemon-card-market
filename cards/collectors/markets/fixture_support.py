from datetime import datetime
from urllib.parse import urlparse

from cards.collectors import (
    ExternalAPIError,
    InvalidResponseError,
    MarketData,
    MissingFieldError,
    RequestSafetyPolicy,
)
from cards.services.normalization import parse_krw_price


class DisabledPublicMarketCollector:
    """접근 정책 확인 전 HTTP 호출을 차단하고 순수 정규화만 제공한다."""

    SOURCE = ''
    HTTP_ENABLED = False
    REQUEST_POLICY = RequestSafetyPolicy(max_items=3)

    def collect(self, *args, **kwargs):
        raise ExternalAPIError(
            f'{self.SOURCE} 자동 수집은 공개 접근 및 이용 조건 확인 전까지 비활성화되어 있습니다.'
        )

    @classmethod
    def _normalize(cls, item, listing_type, require_occurred_at=False):
        if not isinstance(item, dict):
            raise InvalidResponseError(f'{cls.SOURCE} fixture 형식이 올바르지 않습니다.')

        required = ('external_id', 'title', 'price', 'url', 'collected_at')
        missing = [name for name in required if item.get(name) in (None, '')]
        if missing:
            raise MissingFieldError(
                f"{cls.SOURCE} fixture 필수 필드가 없습니다: {', '.join(missing)}"
            )

        external_id = str(item['external_id']).strip()
        title = str(item['title']).strip()
        if not external_id or not title:
            raise MissingFieldError(f'{cls.SOURCE} external_id와 title은 비어 있을 수 없습니다.')

        price = parse_krw_price(item['price'])

        url = _http_url(item['url'], required=True)
        image_url = _http_url(item.get('image_url'), required=False)
        occurred_at = item.get('occurred_at')
        collected_at = item['collected_at']
        if not isinstance(collected_at, datetime):
            raise InvalidResponseError(f'{cls.SOURCE} collected_at은 datetime이어야 합니다.')
        if require_occurred_at and not isinstance(occurred_at, datetime):
            raise InvalidResponseError(
                f'{cls.SOURCE} 완료 결과에는 확인된 occurred_at이 필요합니다.'
            )
        if occurred_at is not None and not isinstance(occurred_at, datetime):
            raise InvalidResponseError(f'{cls.SOURCE} occurred_at은 datetime이어야 합니다.')

        return MarketData(
            external_id=external_id,
            title=title,
            price=price,
            currency='KRW',
            url=url,
            image_url=image_url,
            listing_type=listing_type,
            occurred_at=occurred_at,
            collected_at=collected_at,
            source=cls.SOURCE,
        )


def _http_url(value, required):
    if value in (None, '') and not required:
        return ''
    parsed = urlparse(value) if isinstance(value, str) else None
    if (
        not parsed
        or parsed.scheme not in ('http', 'https')
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise InvalidResponseError('공개 HTTP/HTTPS URL 형식이 올바르지 않습니다.')
    return value
