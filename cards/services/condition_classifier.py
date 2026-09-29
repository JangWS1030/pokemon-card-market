import re
from dataclasses import dataclass
from decimal import Decimal

from cards.models import Condition

from .normalization import normalize_text


@dataclass(frozen=True, slots=True)
class ConditionResult:
    condition: str
    grading_company: str | None = None
    grading_score: Decimal | None = None


GRADE_PATTERN = re.compile(
    r'(?<![a-z0-9])(psa|bgs|cgc)\s*-?\s*(10(?:\.0)?|[1-9](?:\.\d)?)(?![\d.])',
    re.IGNORECASE,
)
BUNDLE_PATTERN = re.compile(
    r'(?<![a-z0-9])(lot|bundle|bulk|collection|playset|x\s*\d+|\d+\s*cards?'
    r'|random\s+card|complete\s+set|you\s+pick)(?![a-z0-9])'
    r'|묶음|일괄|랜덤|대량|완전\s*세트|풀\s*세트|(?:[2-9]|[1-9]\d+)\s*장',
    re.IGNORECASE,
)
SEALED_PATTERN = re.compile(
    r'(?<![a-z0-9])(sealed|unopened|factory sealed|booster box)(?![a-z0-9])|미개봉',
    re.IGNORECASE,
)
RAW_PATTERN = re.compile(r'(?<![a-z0-9])(raw|ungraded)(?![a-z0-9])', re.IGNORECASE)
COMPANY_PATTERN = re.compile(r'(?<![a-z0-9])(psa|bgs|cgc)(?![a-z0-9])', re.IGNORECASE)


def is_bundle_listing(title):
    return bool(BUNDLE_PATTERN.search(normalize_text(title)))


def classify_condition(title, card_matched=False):
    normalized_title = normalize_text(title)
    if not normalized_title or BUNDLE_PATTERN.search(normalized_title):
        return ConditionResult(Condition.UNKNOWN)

    grade_match = GRADE_PATTERN.search(normalized_title)
    if grade_match:
        company = grade_match.group(1).upper()
        score = Decimal(grade_match.group(2))
        if Decimal('1') <= score <= Decimal('10'):
            return ConditionResult(company, company, score)
        return ConditionResult(Condition.UNKNOWN)

    if COMPANY_PATTERN.search(normalized_title):
        return ConditionResult(Condition.UNKNOWN)
    if SEALED_PATTERN.search(normalized_title):
        return ConditionResult(Condition.SEALED)
    if RAW_PATTERN.search(normalized_title) or card_matched:
        return ConditionResult(Condition.RAW)
    return ConditionResult(Condition.UNKNOWN)
