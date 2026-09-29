from django.contrib import admin

from .models import Card, MarketListing, MarketSource, PriceHistory


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = (
        'name_ko',
        'set_name',
        'card_number',
        'rarity',
        'language',
        'source',
    )
    search_fields = ('name_ko', 'name_en', 'set_name', 'card_number')
    list_filter = ('rarity', 'language', 'source')


@admin.register(MarketSource)
class MarketSourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'market_region', 'is_active')
    search_fields = ('name', 'code')
    list_filter = ('market_region', 'is_active')


@admin.register(MarketListing)
class MarketListingAdmin(admin.ModelAdmin):
    list_display = (
        'card',
        'market_source',
        'listing_type',
        'price',
        'currency',
        'condition',
        'grading_company',
        'grading_score',
        'is_active',
        'collected_at',
    )
    search_fields = (
        'title',
        'external_id',
        'card__name_ko',
        'card__card_number',
        'market_source__name',
    )
    list_filter = (
        'market_source',
        'listing_type',
        'currency',
        'condition',
        'grading_company',
        'is_active',
    )


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = (
        'card',
        'listing_type',
        'condition',
        'grading_score',
        'currency',
        'median_price',
        'average_price',
        'listing_count',
        'calculated_at',
    )
    search_fields = ('card__name_ko', 'card__card_number')
    list_filter = ('listing_type', 'condition', 'grading_score', 'currency', 'calculated_at')
