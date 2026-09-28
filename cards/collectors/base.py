from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class CardData:
    """Collector가 프로젝트 내부로 전달하는 공통 카드 데이터다."""

    name_ko: str
    set_name: str
    card_number: str
    language: str
    source: str
    external_id: str | None = None
    name_en: str | None = None
    rarity: str | None = None
    image_url: str | None = None


class CardDataCollector:
    """실제 데이터 출처가 확정된 뒤 구현할 Collector의 기본 형태다."""

    def fetch(self) -> list[Any]:
        raise NotImplementedError('외부 카드 데이터 수집 방법이 설정되지 않았습니다.')

    def normalize(self, raw_card: Any) -> CardData:
        raise NotImplementedError('외부 카드 데이터 정규화 방법이 설정되지 않았습니다.')

    def collect(self) -> list[CardData]:
        return [self.normalize(raw_card) for raw_card in self.fetch()]


@dataclass(frozen=True, slots=True)
class MarketData:
    """판매 데이터 Collector가 반환하는 공통 형식이다."""

    external_id: str
    title: str
    price: Decimal
    currency: str
    url: str
    collected_at: datetime
    source: str
    image_url: str = ''


class MarketCollectorError(Exception):
    """외부 판매 데이터 수집 중 발생한 안전하게 표시 가능한 오류다."""


class MissingCredentialsError(MarketCollectorError):
    pass


class AuthenticationError(MarketCollectorError):
    pass


class RateLimitError(MarketCollectorError):
    pass


class CollectorTimeoutError(MarketCollectorError):
    pass


class ExternalAPIError(MarketCollectorError):
    pass


class InvalidResponseError(MarketCollectorError):
    pass


class MissingFieldError(InvalidResponseError):
    pass
