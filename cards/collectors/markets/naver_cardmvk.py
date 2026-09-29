from cards.collectors import InvalidResponseError

from .fixture_support import DisabledPublicMarketCollector


class NaverCafeCardmvkCollector(DisabledPublicMarketCollector):
    SOURCE = 'NAVER_CARDMVK'

    @classmethod
    def normalize(cls, item):
        board_type = item.get('board_type') if isinstance(item, dict) else None
        if board_type == 'TRADE':
            return cls._normalize(item, 'CURRENT_LISTING')
        if board_type == 'AUCTION_RESULT' and item.get('final_result_confirmed') is True:
            return cls._normalize(item, 'AUCTION_RESULT', require_occurred_at=True)
        raise InvalidResponseError(
            'NAVER CardMVK는 공개 트레이드 또는 명확한 최종 경매 결과만 정규화할 수 있습니다.'
        )
