from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cards', '0003_alter_marketlisting_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='marketlisting',
            name='image_url',
            field=models.URLField(blank=True, default='', max_length=2048),
        ),
    ]
