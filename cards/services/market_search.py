def build_ebay_search_query(card):
    """Card에 실제로 저장된 정보만 사용해 eBay 검색어를 만든다."""

    parts = []
    card_name = card.name_en or card.name_ko
    for value in (card_name, card.card_number, card.set_name, 'Pokemon'):
        if value and value.strip() and value.strip() not in parts:
            parts.append(value.strip())
    return ' '.join(parts)
