from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import AuditEvent, Center, Membership, OrderTest, Patient, TestCatalog, TestOrder


class CenterWorkflowTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.lab_user = user_model.objects.create_user(username="tech", password="safe-test-password")
        self.reviewer = user_model.objects.create_user(
            username="reviewer", password="safe-test-password"
        )
        self.center = Center.objects.create(name="Northside Demo Lab")
        Membership.objects.create(
            user=self.lab_user, center=self.center, role=Membership.Role.LAB_TECH
        )
        Membership.objects.create(
            user=self.reviewer, center=self.center, role=Membership.Role.REVIEWER
        )
        self.patient = Patient.objects.create(
            center=self.center,
            full_name="Alex Example",
            sex=Patient.Sex.UNDISCLOSED,
        )
        self.test = TestCatalog.objects.create(
            center=self.center,
            code="DEMO-1",
            name="Synthetic Demo Test",
            unit="units",
            reference_range="demo only",
        )
        self.order = TestOrder.objects.create(
            center=self.center,
            patient=self.patient,
            created_by=self.lab_user,
        )
        OrderTest.objects.create(order=self.order, test=self.test)
        self.client.login(username="tech", password="safe-test-password")

    def test_patient_list_only_contains_selected_centers_patients(self):
        other_center = Center.objects.create(name="Other Demo Lab")
        Patient.objects.create(center=other_center, full_name="Other Tenant Person")

        response = self.client.get(reverse("patient_list"))

        self.assertContains(response, "Alex Example")
        self.assertNotContains(response, "Other Tenant Person")

    def test_order_from_another_center_is_not_accessible(self):
        other_center = Center.objects.create(name="Other Demo Lab")
        other_patient = Patient.objects.create(center=other_center, full_name="Other Tenant Person")
        other_order = TestOrder.objects.create(
            center=other_center,
            patient=other_patient,
            created_by=self.lab_user,
        )

        response = self.client.get(reverse("order_detail", args=(other_order.pk,)))

        self.assertEqual(response.status_code, 404)

    def test_records_cannot_be_linked_across_centers(self):
        other_center = Center.objects.create(name="Other Demo Lab")
        other_patient = Patient.objects.create(center=other_center, full_name="Other Tenant Person")
        other_test = TestCatalog.objects.create(
            center=other_center,
            code="OTHER-1",
            name="Other Center Test",
        )

        with self.assertRaises(ValidationError):
            TestOrder.objects.create(
                center=self.center,
                patient=other_patient,
                created_by=self.lab_user,
            )
        with self.assertRaises(ValidationError):
            OrderTest.objects.create(order=self.order, test=other_test)

    def test_result_requires_review_before_report_is_available(self):
        detail_url = reverse("order_detail", args=(self.order.pk,))
        self.client.post(detail_url, {"action": "collect"})
        response = self.client.post(detail_url, {"action": "save_results", f"result_{self.order.items.get().pk}": "12.4"})
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, TestOrder.Status.READY_FOR_REVIEW)

        report_url = reverse("order_report", args=(self.order.pk,))
        self.assertEqual(self.client.get(report_url).status_code, 404)
        self.assertEqual(self.client.post(detail_url, {"action": "release"}).status_code, 403)

        self.client.logout()
        self.client.login(username="reviewer", password="safe-test-password")
        response = self.client.post(detail_url, {"action": "release"})

        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, TestOrder.Status.RELEASED)
        self.assertContains(self.client.get(report_url), "12.4")
        self.assertTrue(
            AuditEvent.objects.filter(
                center=self.center,
                actor=self.reviewer,
                order=self.order,
                action="results_released",
            ).exists()
        )
