from collections import defaultdict

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from .models import Card


def health(request):
    return JsonResponse({'status': 'ok'})


def home(request):
    recent_cards = Card.objects.order_by('-created_at')[:8]
    has_real_cards = Card.objects.exclude(source='DEMO').exists()
    has_real_prices = Card.objects.exclude(source='DEMO').filter(
        market_listings__isnull=False
    ).exists()
    return render(
        request,
        'cards/home.html',
        {
            'cards': recent_cards,
            'has_real_cards': has_real_cards,
            'has_real_prices': has_real_prices,
            'has_demo_cards': Card.objects.filter(source='DEMO').exists(),
        },
    )


def card_list(request):
    query = request.GET.get('q', '').strip()
    cards = Card.objects.order_by('name_ko', 'set_name', 'card_number')

    if query:
        cards = cards.filter(
            Q(name_ko__icontains=query)
            | Q(name_en__icontains=query)
            | Q(set_name__icontains=query)
            | Q(card_number__icontains=query)
        )

    page_obj = Paginator(cards, 24).get_page(request.GET.get('page'))
    return render(
        request,
        'cards/card_list.html',
        {'page_obj': page_obj, 'query': query},
    )


def card_detail(request, pk):
    card = get_object_or_404(Card, pk=pk)
    market_listings = list(
        card.market_listings.filter(is_active=True)
        .select_related('market_source')
        .order_by('-collected_at')
    )
    price_histories = list(
        card.price_histories.exclude(condition='UNKNOWN').order_by('-calculated_at')
    )

    context = {
        'card': card,
        'market_listings': market_listings,
        'price_histories': price_histories,
        'latest_listing': market_listings[0] if market_listings else None,
        'latest_price_history': price_histories[0] if price_histories else None,
        'price_chart_data': _build_price_chart_data(reversed(price_histories)),
        'is_demo': card.source == 'DEMO',
    }
    return render(request, 'cards/card_detail.html', context)


def _build_price_chart_data(price_histories):
    grouped_points = defaultdict(list)
    for history in price_histories:
        grade = f' {history.grading_score}' if history.grading_score is not None else ''
        label = f'{history.condition}{grade} / {history.currency}'
        grouped_points[label].append(
            {
                'x': history.calculated_at.isoformat(),
                'y': float(history.median_price),
            }
        )

    colors = ('#0d6efd', '#dc3545', '#198754', '#6f42c1', '#fd7e14', '#20c997')
    datasets = []
    for index, (label, points) in enumerate(grouped_points.items()):
        datasets.append(
            {
                'label': label,
                'data': points,
                'borderColor': colors[index % len(colors)],
                'backgroundColor': colors[index % len(colors)],
                'tension': 0.2,
            }
        )
    return {'datasets': datasets}
