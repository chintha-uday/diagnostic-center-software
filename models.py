from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Center(models.Model):
    name = models.CharField(max_length=160)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        CENTER_ADMIN = "center_admin", "Center admin"
        FRONT_DESK = "front_desk", "Front desk"
        LAB_TECH = "lab_tech", "Lab technician"
        REVIEWER = "reviewer", "Result reviewer"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "center"), name="unique_center_membership")
        ]

    def __str__(self):
        return f"{self.user} - {self.center} ({self.get_role_display()})"


class Patient(models.Model):
    class Sex(models.TextChoices):
        FEMALE = "F", "Female"
        MALE = "M", "Male"
        OTHER = "X", "Other"
        UNDISCLOSED = "U", "Undisclosed"

    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name="patients")
    patient_code = models.CharField(max_length=24, blank=True)
    full_name = models.CharField(max_length=160)
    date_of_birth = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=1, choices=Sex.choices, default=Sex.UNDISCLOSED)
    phone = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("full_name",)
        constraints = [
            models.UniqueConstraint(fields=("center", "patient_code"), name="unique_patient_code_per_center")
        ]

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.patient_code:
            self.patient_code = f"P-{self.pk:06d}"
            super().save(update_fields=("patient_code",))

    def __str__(self):
        return f"{self.patient_code} — {self.full_name}"


class TestCatalog(models.Model):
    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name="tests")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=160)
    unit = models.CharField(max_length=40, blank=True)
    reference_range = models.CharField(max_length=120, blank=True)
    price = models.DecimalField(max_digits=9, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=("center", "code"), name="unique_test_code_per_center")
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"


class TestOrder(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Order received"
        COLLECTED = "collected", "Sample collected"
        IN_PROGRESS = "in_progress", "Processing"
        READY_FOR_REVIEW = "ready_for_review", "Ready for review"
        RELEASED = "released", "Released"

    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name="orders")
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="orders")
    order_number = models.CharField(max_length=24, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.RECEIVED)
    notes = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_orders"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("center", "order_number"), name="unique_order_number_per_center")
        ]

    def clean(self):
        if self.patient_id and self.center_id and self.patient.center_id != self.center_id:
            raise ValidationError({"patient": "Patient and order must belong to the same center."})

    def save(self, *args, **kwargs):
        self.clean()
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.order_number:
            self.order_number = f"O-{self.pk:06d}"
            super().save(update_fields=("order_number",))

    def __str__(self):
        return self.order_number


class OrderTest(models.Model):
    order = models.ForeignKey(TestOrder, on_delete=models.CASCADE, related_name="items")
    test = models.ForeignKey(TestCatalog, on_delete=models.PROTECT)
    result_value = models.CharField(max_length=200, blank=True)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entered_results",
    )
    entered_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_results",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("order", "test"), name="unique_test_per_order")
        ]

    def clean(self):
        if self.order_id and self.test_id and self.order.center_id != self.test.center_id:
            raise ValidationError({"test": "Test and order must belong to the same center."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order} — {self.test.name}"


class AuditEvent(models.Model):
    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name="audit_events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_audit_events",
    )
    order = models.ForeignKey(
        TestOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=40)
    object_type = models.CharField(max_length=32)
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.action} · {self.object_type} #{self.object_id}"
