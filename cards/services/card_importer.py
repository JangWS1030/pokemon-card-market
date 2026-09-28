from dataclasses import dataclass, field
from typing import Iterable

from django.db import IntegrityError, transaction

from cards.collectors import CardData
from cards.models import Card


@dataclass
class CardImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    messages: list[str] = field(default_factory=list)


def import_cards(card_data_items: Iterable[CardData]) -> CardImportResult:
    """정규화된 카드 데이터를 검증한 뒤 Card에 생성하거나 갱신한다."""

    result = CardImportResult()

    for index, card_data in enumerate(card_data_items, start=1):
        if not isinstance(card_data, CardData):
            result.errors += 1
            result.messages.append(f'{index}번째 항목: CardData 형식이 아닙니다.')
            continue

        cleaned_data, validation_error = _clean_card_data(card_data)
        if validation_error:
            result.skipped += 1
            result.messages.append(f'{index}번째 항목: {validation_error}')
            continue

        try:
            with transaction.atomic():
                action = _save_card(cleaned_data)
        except IntegrityError as error:
            result.errors += 1
            result.messages.append(f'{index}번째 항목: DB 제약조건 오류 ({error})')
            continue

        if action == 'created':
            result.created += 1
        elif action == 'updated':
            result.updated += 1
        else:
            result.skipped += 1
            result.messages.append(f'{index}번째 항목: 중복 후보를 하나로 확정할 수 없습니다.')

    return result


def _clean_card_data(card_data: CardData) -> tuple[dict, str | None]:
    required_fields = ('set_name', 'card_number', 'language', 'source')
    cleaned_data = {}

    for field_name in required_fields:
        value = getattr(card_data, field_name)
        if not isinstance(value, str) or not value.strip():
            return {}, f'{field_name} 필수값이 없습니다.'
        cleaned_data[field_name] = value.strip()

    cleaned_data['language'] = cleaned_data['language'].upper()

    cleaned_data['name_ko'] = (
        card_data.name_ko.strip()
        if isinstance(card_data.name_ko, str) and card_data.name_ko.strip()
        else ''
    )

    for field_name in ('external_id', 'name_en', 'rarity', 'image_url'):
        value = getattr(card_data, field_name)
        cleaned_data[field_name] = value.strip() if isinstance(value, str) and value.strip() else None

    if not cleaned_data['name_ko'] and not cleaned_data['name_en']:
        return {}, 'name_ko 또는 name_en 중 하나는 필요합니다.'

    return cleaned_data, None


def _save_card(card_data: dict) -> str:
    external_id = card_data['external_id']

    if external_id:
        card = Card.objects.filter(
            source=card_data['source'],
            external_id=external_id,
        ).first()
        if card:
            _update_card(card, card_data)
            return 'updated'

    candidates = Card.objects.filter(
        source=card_data['source'],
        set_name=card_data['set_name'],
        card_number=card_data['card_number'],
        language=card_data['language'],
    )

    if candidates.count() > 1:
        if card_data['name_ko']:
            candidates = candidates.filter(name_ko=card_data['name_ko'])
        elif card_data['name_en']:
            candidates = candidates.filter(name_en=card_data['name_en'])

    candidate_count = candidates.count()
    if candidate_count > 1:
        return 'skipped'
    if candidate_count == 1:
        _update_card(candidates.first(), card_data)
        return 'updated'

    Card.objects.create(**card_data)
    return 'created'


def _update_card(card: Card, card_data: dict) -> None:
    for field_name, value in card_data.items():
        if value is not None or field_name in {
            'name_ko',
            'set_name',
            'card_number',
            'language',
            'source',
        }:
            setattr(card, field_name, value)
    card.save()
