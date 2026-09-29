import re
import unicodedata
from decimal import Decimal, InvalidOperation

from cards.collectors import InvalidResponseError


KRW_PRICE_PATTERN = re.compile(
    r'^(?:₩\s*|krw\s*)?(\d{1,3}(?:,\d{3})+|\d+)(?:\s*원)?$',
    re.IGNORECASE,
)


def normalize_text(value):
    """원본은 보존하고 비교용 문자열만 단순하게 정규화한다."""

    if not isinstance(value, str):
        return ''
    normalized = unicodedata.normalize('NFKC', value).casefold().strip()
    normalized = re.sub(r'[|_,:;()\[\]{}]+', ' ', normalized)
    normalized = re.sub(r'\s*/\s*', '/', normalized)
    normalized = re.sub(r'\s*-\s*', '-', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


def normalize_card_number(value):
    return normalize_text(value).replace(' ', '')


def contains_card_number(text, card_number):
    """문자열에 같은 카드번호가 이미 있는지 비교용 정규화로 확인한다."""

    normalized_number = normalize_card_number(card_number).lstrip('#')
    normalized_text = normalize_text(text)
    if not normalized_number or not normalized_text:
        return False
    return bool(
        re.search(
            rf'(?<![a-z0-9])#?{re.escape(normalized_number)}(?![a-z0-9])',
            normalized_text,
        )
    )


def canonical_card_name(name, card_number):
    """검색용 카드명 끝에 붙은 동일 카드번호만 제거한다."""

    normalized_name = normalize_text(name)
    normalized_number = normalize_card_number(card_number).lstrip('#')
    if not normalized_name or not normalized_number:
        return normalized_name

    suffix = re.compile(
        rf'(?:\s*-\s*|\s+#?\s*){re.escape(normalized_number)}\s*$',
        re.IGNORECASE,
    )
    return suffix.sub('', normalized_name).rstrip(' -#')


def parse_krw_price(value):
    """명시적인 원화 정수 가격만 허용하고 축약 표현은 추측하지 않는다."""

    if isinstance(value, bool) or value is None:
        raise InvalidResponseError('KRW 가격 형식이 올바르지 않습니다.')

    if isinstance(value, (int, Decimal)):
        normalized = str(value)
    elif isinstance(value, str):
        normalized = unicodedata.normalize('NFKC', value).strip()
    else:
        raise InvalidResponseError('KRW 가격 형식이 올바르지 않습니다.')

    match = KRW_PRICE_PATTERN.fullmatch(normalized)
    if not match:
        raise InvalidResponseError('KRW 가격 형식이 올바르지 않습니다.')

    try:
        price = Decimal(match.group(1).replace(',', ''))
    except InvalidOperation as error:
        raise InvalidResponseError('KRW 가격 형식이 올바르지 않습니다.') from error
    if price <= 0 or price != price.to_integral_value():
        raise InvalidResponseError('KRW 가격은 0보다 큰 정수여야 합니다.')
    return price
