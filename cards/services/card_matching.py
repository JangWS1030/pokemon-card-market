import re

from .condition_classifier import is_bundle_listing
from .normalization import canonical_card_name, normalize_card_number, normalize_text


CARD_NUMBER_PATTERN = re.compile(r'(?<!\d)#?\d{1,4}\s*/\s*\d{1,4}(?!\d)')


def is_listing_relevant_to_card(card, title):
    """단일 카드 매물 제목이 대상 카드와 관련 있는지 보수적으로 판정한다."""

    normalized_title = normalize_text(title)
    if not normalized_title or is_bundle_listing(normalized_title):
        return False

    is_korean_card = str(card.language).upper() in ('KO', 'KR')
    names = (card.name_ko,) if is_korean_card else (card.name_en, card.name_ko)
    canonical_names = [
        canonical_card_name(name, card.card_number)
        for name in names
        if canonical_card_name(name, card.card_number)
    ]
    if not any(_phrase_matches(name, normalized_title) for name in canonical_names):
        return False

    target_number = normalize_card_number(card.card_number).lstrip('#')
    title_numbers = {
        normalize_card_number(match.group()).lstrip('#')
        for match in CARD_NUMBER_PATTERN.finditer(normalized_title)
    }
    if title_numbers and (not target_number or title_numbers != {target_number}):
        return False
    if is_korean_card and not title_numbers:
        normalized_set = normalize_text(card.set_name)
        if not normalized_set or normalized_set not in normalized_title:
            return False
    return True


def match_card(title, candidates):
    """상품 제목에서 정확히 한 카드만 확정될 때 Card를 반환한다."""

    cards = list(candidates)
    normalized_title = normalize_text(title)
    if not normalized_title or not cards:
        return None

    number_matches = [card for card in cards if _card_number_matches(card, normalized_title)]
    if number_matches:
        return _refine_candidates(number_matches, normalized_title)

    name_matches = [card for card in cards if _card_name_matches(card, normalized_title)]
    if not name_matches:
        return None
    return _refine_candidates(name_matches, normalized_title, skip_name=True)


def _refine_candidates(candidates, normalized_title, skip_name=False):
    remaining = candidates
    refiners = []
    if not skip_name:
        refiners.append(_card_name_matches)
    refiners.extend((_set_name_matches, _language_matches, _rarity_matches))

    for refiner in refiners:
        matched = [card for card in remaining if refiner(card, normalized_title)]
        if matched:
            remaining = matched
        if len(remaining) == 1:
            return remaining[0]

    return remaining[0] if len(remaining) == 1 else None


def _card_number_matches(card, normalized_title):
    card_number = normalize_card_number(card.card_number)
    if not card_number:
        return False
    return bool(re.search(rf'(?<![a-z0-9]){re.escape(card_number)}(?![a-z0-9])', normalized_title))


def _card_name_matches(card, normalized_title):
    names = (card.name_en, card.name_ko)
    canonical_names = [canonical_card_name(name, card.card_number) for name in names]
    return any(_phrase_matches(name, normalized_title) for name in canonical_names if name)


def _phrase_matches(phrase, normalized_title):
    return bool(
        re.search(
            rf'(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])',
            normalized_title,
        )
    )


def _set_name_matches(card, normalized_title):
    set_name = normalize_text(card.set_name)
    return bool(set_name and set_name in normalized_title)


def _language_matches(card, normalized_title):
    language_words = {
        'EN': ('english',),
        'KO': ('korean', '한국어', '한글'),
        'KR': ('korean', '한국어', '한글'),
        'JP': ('japanese', '일본어', '일판'),
        'JA': ('japanese', '일본어', '일판'),
    }
    words = language_words.get(str(card.language).upper(), ())
    return any(
        re.search(rf'(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])', normalized_title)
        for word in words
    )


def _rarity_matches(card, normalized_title):
    rarity = normalize_text(card.rarity)
    if not rarity:
        return False
    return bool(re.search(rf'(?<![a-z0-9]){re.escape(rarity)}(?![a-z0-9])', normalized_title))
