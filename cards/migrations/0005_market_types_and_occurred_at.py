from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cards', '0004_marketlisting_image_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='marketlisting',
            name='listing_type',
            field=models.CharField(
                choices=[
                    ('CURRENT_LISTING', '현재 매물'),
                    ('SOLD', '판매 완료'),
                    ('AUCTION_RESULT', '경매 결과'),
                ],
                default='CURRENT_LISTING',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='marketlisting',
            name='occurred_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pricehistory',
            name='listing_type',
            field=models.CharField(
                choices=[
                    ('CURRENT_LISTING', '현재 매물'),
                    ('SOLD', '판매 완료'),
                    ('AUCTION_RESULT', '경매 결과'),
                ],
                default='CURRENT_LISTING',
                max_length=20,
            ),
        ),
    ]
