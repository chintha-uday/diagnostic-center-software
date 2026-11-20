from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from lab.models import Center, Membership, TestCatalog


class Command(BaseCommand):
    help = "Create a center, assign an existing user, and add a starter test catalog."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--username", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["username"]).first()
        if user is None:
            raise CommandError(f"User {options['username']!r} does not exist. Create it first.")

        center, created = Center.objects.get_or_create(name=options["name"])
        Membership.objects.update_or_create(
            user=user,
            center=center,
            defaults={"role": Membership.Role.CENTER_ADMIN},
        )
        starter_tests = (
            ("CBC", "Complete Blood Count", "", ""),
            ("GLU-F", "Glucose, Fasting", "mg/dL", "70-99"),
            ("TSH", "Thyroid Stimulating Hormone", "mIU/L", "0.4-4.0"),
        )
        for code, name, unit, reference_range in starter_tests:
            TestCatalog.objects.get_or_create(
                center=center,
                code=code,
                defaults={
                    "name": name,
                    "unit": unit,
                    "reference_range": reference_range,
                },
            )
        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} setup for {center.name}."))
