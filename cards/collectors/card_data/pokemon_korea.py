from urllib.parse import urlparse

from cards.collectors import CardData, ExternalAPIError, MissingFieldError


class PokemonKoreaCardCollector:
    """공식 사이트 사용 허가 확인 전에는 HTTP를 수행하지 않는 정규화 경계다."""

    SOURCE = 'POKEMON_KOREA'
    HTTP_ENABLED = False

    def collect(self, *args, **kwargs):
        raise ExternalAPIError(
            'Pokémon Korea 자동 수집은 이용 조건과 이미지 사용 정책 확인 전까지 비활성화되어 있습니다.'
        )

    @classmethod
    def normalize(cls, item):
        if not isinstance(item, dict):
            raise MissingFieldError('Pokémon Korea 카드 데이터 형식이 올바르지 않습니다.')

        required = ('external_id', 'name_ko', 'set_name', 'card_number')
        missing = [name for name in required if not _clean_text(item.get(name))]
        if missing:
            raise MissingFieldError(
                f"Pokémon Korea 카드 필수 필드가 없습니다: {', '.join(missing)}"
            )

        image_url = _public_url_or_empty(item.get('image_url'))
        return CardData(
            external_id=_clean_text(item['external_id']),
            name_ko=_clean_text(item['name_ko']),
            name_en=_clean_text(item.get('name_en')) or None,
            set_name=_clean_text(item['set_name']),
            card_number=_clean_text(item['card_number']),
            rarity=_clean_text(item.get('rarity')) or None,
            language='KO',
            image_url=image_url,
            source=cls.SOURCE,
        )


def _clean_text(value):
    return value.strip() if isinstance(value, str) else ''


def _public_url_or_empty(value):
    value = _clean_text(value)
    return value if value and urlparse(value).scheme in ('http', 'https') else ''
