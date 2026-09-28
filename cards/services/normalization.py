import re
import unicodedata


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
