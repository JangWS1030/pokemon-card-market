from cards.collectors import InvalidResponseError

from .fixture_support import DisabledPublicMarketCollector


class BunjangMarketCollector(DisabledPublicMarketCollector):
    SOURCE = 'BUNJANG'

    @classmethod
    def normalize(cls, item):
        if not isinstance(item, dict) or item.get('data_type') != 'CURRENT_LISTING':
            raise InvalidResponseError(
                '번개장터는 현재 공개 매물만 정규화하며 판매완료를 실거래로 추정하지 않습니다.'
            )
        return cls._normalize(item, 'CURRENT_LISTING')
