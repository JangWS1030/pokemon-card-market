import re
import ipaddress
from html.parser import HTMLParser
from urllib.parse import urlparse

from cards.collectors import (
    CardData,
    ExternalAPIError,
    InvalidResponseError,
    MissingFieldError,
    RequestSafetyPolicy,
)
from cards.collectors.public_http import PublicHttpClient
from cards.services.normalization import canonical_card_name, normalize_card_number, normalize_text


PUBLIC_PAGE_HOSTS = {'pokemoncard.co.kr', 'www.pokemoncard.co.kr'}
OFFICIAL_IMAGE_HOSTS = {'cards.image.pokemonkorea.co.kr'}
MAX_IMAGE_URL_LENGTH = 2048
DETAIL_PATH_PATTERN = re.compile(r'^/cards/detail/(?P<external_id>[A-Za-z0-9_-]+)/*$')
NUMBER_PATTERN = re.compile(r'(?P<number>\d{1,4}\s*/\s*\d{1,4})(?:\s+(?P<rarity>\S+))?')


class _PokemonKoreaDetailParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.name_parts = []
        self.number_parts = []
        self.set_parts = []
        self.image_url = ''
        self._capture = None
        self._capture_tag = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set(attributes.get('class', '').split())
        if tag == 'img' and 'feature_image' in classes:
            self.image_url = attributes.get('src', '').strip()
        elif tag == 'span' and {'card-hp', 'title'} <= classes:
            self._capture, self._capture_tag = self.name_parts, tag
        elif tag == 'span' and 'p_num' in classes:
            self._capture, self._capture_tag = self.number_parts, tag
        elif tag == 'a' and attributes.get('href', '').startswith('/cards?s='):
            self._capture, self._capture_tag = self.set_parts, tag

    def handle_endtag(self, tag):
        if tag == self._capture_tag:
            self._capture = None
            self._capture_tag = None

    def handle_data(self, data):
        if self._capture is not None:
            self._capture.append(data)


class PokemonKoreaCardCollector:
    """Explicit public-detail lookup for official Korean card images."""

    SOURCE = 'POKEMON_KOREA'
    HTTP_ENABLED = False
    REQUEST_POLICY = RequestSafetyPolicy(max_items=3, request_budget=6, retry_limit=0)

    def __init__(self, client=None):
        self.client = client or PublicHttpClient(
            PUBLIC_PAGE_HOSTS | OFFICIAL_IMAGE_HOSTS,
            policy=self.REQUEST_POLICY,
        )

    @property
    def request_count(self):
        return self.client.request_count

    def collect_url(self, url, check_image=False):
        raise ExternalAPIError(
            'Pokemon Korea automatic public-page collection is disabled because '
            'the verified user environment returned HTTP 410.'
        )

    @classmethod
    def parse_detail_html(cls, url, html):
        """Preserved pure parser for a future officially usable public response."""
        parsed_url = urlparse(url)
        path_match = DETAIL_PATH_PATTERN.fullmatch(parsed_url.path)
        if parsed_url.hostname not in PUBLIC_PAGE_HOSTS or not path_match:
            raise InvalidResponseError('Pokémon Korea 카드 상세 공개 URL만 허용합니다.')

        parser = _PokemonKoreaDetailParser()
        parser.feed(html)
        number_text = _clean_text(' '.join(parser.number_parts))
        number_match = NUMBER_PATTERN.search(number_text)
        item = {
            'external_id': path_match.group('external_id'),
            'name_ko': _clean_text(' '.join(parser.name_parts)),
            'set_name': _clean_text(' '.join(parser.set_parts)),
            'card_number': number_match.group('number') if number_match else '',
            'rarity': number_match.group('rarity') if number_match else '',
            'image_url': parser.image_url,
        }
        data = cls.normalize(item)
        if not data.image_url:
            raise InvalidResponseError('공식 상세 페이지에서 허용된 이미지 URL을 찾지 못했습니다.')
        return data

    def collect_urls(self, urls, check_image=False):
        urls = list(urls)
        if not 1 <= len(urls) <= self.REQUEST_POLICY.max_items:
            raise InvalidResponseError('한 번에 1~3개의 카드 상세 URL만 조회할 수 있습니다.')
        return [self.collect_url(url, check_image=check_image) for url in urls]

    @classmethod
    def matches_card(cls, card, data):
        if normalize_card_number(card.card_number) != normalize_card_number(data.card_number):
            return False

        expected_name = canonical_card_name(card.name_ko or card.name_en, card.card_number)
        actual_name = canonical_card_name(data.name_ko, data.card_number)
        if card.name_ko and expected_name != actual_name:
            return False

        expected_tokens = _identity_tokens(card.set_name)
        actual_tokens = _identity_tokens(data.set_name)
        return bool(expected_tokens & actual_tokens)

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
            card_number=_clean_text(item['card_number']).replace(' ', ''),
            rarity=_clean_text(item.get('rarity')) or None,
            language='KO',
            image_url=image_url,
            source=cls.SOURCE,
        )


def _clean_text(value):
    return re.sub(r'\s+', ' ', value).strip() if isinstance(value, str) else ''


def _identity_tokens(value):
    return {
        token
        for token in re.findall(r'[a-z0-9가-힣]+', normalize_text(value))
        if len(token) >= 2
    }


def _public_url_or_empty(value):
    try:
        return validate_official_image_url(value)
    except InvalidResponseError:
        return ''


def validate_official_image_url(value):
    value = _clean_text(value)
    if not value or len(value) > MAX_IMAGE_URL_LENGTH or any(char.isspace() for char in value):
        raise InvalidResponseError('공식 이미지 URL 형식 또는 길이가 올바르지 않습니다.')
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise InvalidResponseError('공식 이미지 URL port가 올바르지 않습니다.') from error
    hostname = parsed.hostname.casefold() if parsed.hostname else ''
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if (
        parsed.scheme == 'https'
        and hostname in OFFICIAL_IMAGE_HOSTS
        and not parsed.username
        and not parsed.password
        and port in (None, 443)
        and address is None
    ):
        return value
    raise InvalidResponseError(
        'HTTPS cards.image.pokemonkorea.co.kr 이미지 URL만 허용합니다.'
    )
