from cards.collectors import InvalidResponseError

from .fixture_support import DisabledPublicMarketCollector


class KreamMarketCollector(DisabledPublicMarketCollector):
    SOURCE = 'KREAM'

    @classmethod
    def normalize(cls, item):
        data_type = item.get('data_type') if isinstance(item, dict) else None
        if data_type == 'CURRENT_LISTING':
            return cls._normalize(item, 'CURRENT_LISTING')
        if data_type == 'SOLD' and item.get('transaction_confirmed') is True:
            return cls._normalize(item, 'SOLD', require_occurred_at=True)
        raise InvalidResponseError(
            'KREAM 데이터는 확인된 현재 판매 입찰 또는 체결 거래만 정규화할 수 있습니다.'
        )
