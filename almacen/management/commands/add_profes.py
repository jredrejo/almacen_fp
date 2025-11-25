from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group


class Command(BaseCommand):
    help = "Add users (by email) to ProfesoresFP group. Usage: python manage.py add_teachers emails.txt"

    def add_arguments(self, parser):
        parser.add_argument("file", help="Text file with one email per line")

    def handle(self, file, *args, **kwargs):
        User = get_user_model()
        group, _ = Group.objects.get_or_create(name="ProfesoresFP")
        added, missing = 0, []
        with open(file, "r", encoding="utf-8") as f:
            for raw in f:
                email = raw.strip().lower()
                if not email:
                    continue
                try:
                    user = User.objects.get(email__iexact=email)
                except User.DoesNotExist:
                    missing.append(email)
                    continue
                user.groups.add(group)
                added += 1
        self.stdout.write(self.style.SUCCESS(f"Added {added} users to ProfesoresFP"))
        if missing:
            self.stdout.write(
                self.style.WARNING(
                    f"Missing users (create them first): {', '.join(missing)}"
                )
            )
