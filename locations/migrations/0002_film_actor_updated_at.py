from django.db import migrations, models
from django.db.models import F
from django.utils import timezone


def init_film_updated_at(apps, schema_editor):
    # Les films existants gardent leur ordre : dernier import = date de création
    Film = apps.get_model('locations', 'Film')
    Film.objects.update(updated_at=F('created_at'))


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='film',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, default=timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='actor',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, default=timezone.now),
            preserve_default=False,
        ),
        migrations.RunPython(init_film_updated_at, migrations.RunPython.noop),
    ]
