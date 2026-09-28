from django.db import models

from cards.services.normalization import contains_card_number


class Condition(models.TextChoices):
    RAW = 'RAW', 'RAW'
    PSA = 'PSA', 'PSA'
    BGS = 'BGS', 'BGS'
    CGC = 'CGC', 'CGC'
    SEALED = 'SEALED', 'SEALED'
    UNKNOWN = 'UNKNOWN', 'UNKNOWN'


class GradingCompany(models.TextChoices):
    PSA = 'PSA', 'PSA'
    BGS = 'BGS', 'BGS'
    CGC = 'CGC', 'CGC'


class MarketRegion(models.TextChoices):
    KR = 'KR', '국내'
    GLOBAL = 'GLOBAL', '해외'


class Card(models.Model):
    external_id = models.CharField(max_length=255, null=True, blank=True)
    name_ko = models.CharField(max_length=200)
    name_en = models.CharField(max_length=200, null=True, blank=True)
    set_name = models.CharField(max_length=200)
    card_number = models.CharField(max_length=50)
    rarity = models.CharField(max_length=50, null=True, blank=True)
    language = models.CharField(max_length=20)
    image_url = models.URLField(null=True, blank=True)
    source = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'external_id'],
                name='unique_card_source_external_id',
            ),
        ]

    def __str__(self):
        return f'{self.display_name} / {self.set_name} / {self.card_number}'

    @property
    def display_name(self):
        return self.name_ko or self.name_en or '이름 없음'

    @property
    def display_name_with_number(self):
        name = self.display_name
        if not self.card_number or contains_card_number(name, self.card_number):
            return name
        return f'{name} - {self.card_number}'


class MarketSource(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    base_url = models.URLField(null=True, blank=True)
    market_region = models.CharField(max_length=10, choices=MarketRegion.choices)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.name} ({self.code})'


class MarketListing(models.Model):
    card = models.ForeignKey(
        Card,
        on_delete=models.PROTECT,
        related_name='market_listings',
    )
    market_source = models.ForeignKey(
        MarketSource,
        on_delete=models.PROTECT,
        related_name='market_listings',
    )
    external_id = models.CharField(max_length=255)
    title = models.CharField(max_length=500)
    price = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    url = models.URLField(max_length=2048)
    image_url = models.URLField(max_length=2048, blank=True, default='')
    condition = models.CharField(max_length=10, choices=Condition.choices)
    grading_company = models.CharField(
        max_length=3,
        choices=GradingCompany.choices,
        null=True,
        blank=True,
    )
    grading_score = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    collected_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['market_source', 'external_id'],
                name='unique_listing_source_external_id',
            ),
        ]

    def __str__(self):
        return f'{self.market_source.name} / {self.title}'


class PriceHistory(models.Model):
    card = models.ForeignKey(
        Card,
        on_delete=models.PROTECT,
        related_name='price_histories',
    )
    condition = models.CharField(max_length=10, choices=Condition.choices)
    currency = models.CharField(max_length=3, default='KRW')
    grading_score = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
    )
    calculated_at = models.DateTimeField()
    median_price = models.DecimalField(max_digits=14, decimal_places=2)
    average_price = models.DecimalField(max_digits=14, decimal_places=2)
    min_price = models.DecimalField(max_digits=14, decimal_places=2)
    max_price = models.DecimalField(max_digits=14, decimal_places=2)
    listing_count = models.PositiveIntegerField()

    def __str__(self):
        return f'{self.card} / {self.condition} / {self.calculated_at:%Y-%m-%d %H:%M}'
