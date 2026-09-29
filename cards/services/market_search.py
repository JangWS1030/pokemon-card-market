from .normalization import contains_card_number


def build_ebay_search_query(card):
    """Card에 실제로 저장된 정보만 사용해 eBay 검색어를 만든다."""

    parts = []
    card_name = card.name_en or card.name_ko
    values = [card_name]
    if card.card_number and not contains_card_number(card_name, card.card_number):
        values.append(card.card_number)
    values.extend((card.set_name, 'Pokemon'))

    for value in values:
        if value and value.strip() and value.strip() not in parts:
            parts.append(value.strip())
    return ' '.join(parts)


def build_bunjang_search_query(card):
    """한국어 이름을 우선해 소량 Bunjang 상품 검색어를 만든다."""

    parts = []
    card_name = card.name_ko or card.name_en
    values = [card_name]
    if card.card_number and not contains_card_number(card_name, card.card_number):
        values.append(card.card_number)
    values.append(card.set_name)
    for value in values:
        if value and value.strip() and value.strip() not in parts:
            parts.append(value.strip())
    return ' '.join(parts)
