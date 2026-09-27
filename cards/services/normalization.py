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
