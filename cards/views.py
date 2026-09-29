import hashlib
import json
import os
from collections import defaultdict

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Card, ListingType, MarketRegion


EBAY_DELETION_ENDPOINT = (
    'https://pokemon-card-market.onrender.com/ebay/account-deletion/'
)


def health(request):
    return JsonResponse({'status': 'ok'})


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def ebay_account_deletion(request):
    if request.method == 'GET':
        challenge_code = request.GET.get('challenge_code', '')
        verification_token = os.environ.get(
            'EBAY_DELETION_VERIFICATION_TOKEN',
            '',
        ).strip()
        if not challenge_code:
            return JsonResponse({'error': 'invalid challenge request'}, status=400)
        if not verification_token:
            return JsonResponse({'error': 'webhook is not configured'}, status=503)

        challenge_hash = hashlib.sha256(
            f'{challenge_code}{verification_token}{EBAY_DELETION_ENDPOINT}'.encode('utf-8')
        ).hexdigest()
        return JsonResponse({'challengeResponse': challenge_hash})

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'error': 'invalid JSON'}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({'error': 'invalid notification'}, status=400)

    metadata = payload.get('metadata')
    if metadata is not None and not isinstance(metadata, dict):
        return JsonResponse({'error': 'invalid notification metadata'}, status=400)
    topic = metadata.get('topic') if metadata else None
    if topic is not None and topic != 'MARKETPLACE_ACCOUNT_DELETION':
        return JsonResponse({'error': 'unsupported notification topic'}, status=400)

    return HttpResponse(status=204)


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
    domestic_sold_histories = [
        history
        for history in price_histories
        if history.listing_type == ListingType.SOLD and history.currency == 'KRW'
    ]
    domestic_current_histories = [
        history
        for history in price_histories
        if history.listing_type == ListingType.CURRENT_LISTING and history.currency == 'KRW'
    ]
    auction_result_histories = [
        history
        for history in price_histories
        if history.listing_type == ListingType.AUCTION_RESULT and history.currency == 'KRW'
    ]
    overseas_current_histories = [
        history
        for history in price_histories
        if history.listing_type == ListingType.CURRENT_LISTING and history.currency != 'KRW'
    ]
    domestic_listings = [
        listing
        for listing in market_listings
        if listing.market_source.market_region == MarketRegion.KR
    ]
    ebay_listings = [
        listing for listing in market_listings if listing.market_source.code == 'EBAY'
    ]
    preferred_histories = (
        domestic_sold_histories
        or domestic_current_histories
        or overseas_current_histories
        or auction_result_histories
    )

    context = {
        'card': card,
        'market_listings': market_listings,
        'price_histories': price_histories,
        'domestic_sold_histories': domestic_sold_histories,
        'domestic_current_histories': domestic_current_histories,
        'auction_result_histories': auction_result_histories,
        'overseas_current_histories': overseas_current_histories,
        'domestic_listings': domestic_listings,
        'ebay_listings': ebay_listings,
        'latest_listing': market_listings[0] if market_listings else None,
        'latest_price_history': preferred_histories[0] if preferred_histories else None,
        'price_chart_data': _build_price_chart_data(reversed(price_histories)),
        'is_demo': card.source == 'DEMO',
    }
    return render(request, 'cards/card_detail.html', context)


def _build_price_chart_data(price_histories):
    grouped_points = defaultdict(list)
    for history in price_histories:
        grade = f' {history.grading_score}' if history.grading_score is not None else ''
        label = (
            f'{history.get_listing_type_display()} / '
            f'{history.condition}{grade} / {history.currency}'
        )
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
