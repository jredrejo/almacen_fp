from django.db import migrations

def create_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="ProfesoresFP")

class Migration(migrations.Migration):
    dependencies = [("store", "0001_initial")]
    operations = [migrations.RunPython(create_group, migrations.RunPython.noop)]
