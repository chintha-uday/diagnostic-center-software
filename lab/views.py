from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import PatientForm, TestOrderForm
from .models import AuditEvent, Membership, OrderTest, Patient, TestOrder


def record_audit(request, action, object_type, object_id, order=None, details=None):
    AuditEvent.objects.create(
        center=request.center,
        actor=request.user,
        order=order,
        action=action,
        object_type=object_type,
        object_id=object_id,
        details=details or {},
    )


def active_center(request):
    memberships = Membership.objects.filter(user=request.user).select_related("center")
    selected_id = request.session.get("active_center_id")
    if selected_id:
        membership = memberships.filter(center_id=selected_id).first()
        if membership:
            return membership.center
    if memberships.count() == 1:
        center = memberships.first().center
        request.session["active_center_id"] = center.pk
        return center
    return None


def center_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        center = active_center(request)
        if center is None:
            if Membership.objects.filter(user=request.user).exists():
                return redirect("choose_center")
            return HttpResponseForbidden("Your account is not assigned to a diagnostic center.")
        request.center = center
        request.membership = Membership.objects.get(user=request.user, center=center)
        return view(request, *args, **kwargs)

    return wrapped


def roles_required(*roles):
    def decorate(view):
        @wraps(view)
        @center_required
        def wrapped(request, *args, **kwargs):
            if request.membership.role not in roles:
                return HttpResponseForbidden("Your role cannot perform this action.")
            return view(request, *args, **kwargs)

        return wrapped

    return decorate


@login_required
def choose_center(request):
    memberships = Membership.objects.filter(user=request.user).select_related("center")
    if request.method == "POST":
        membership = memberships.filter(center_id=request.POST.get("center_id")).first()
        if membership is None:
            raise Http404("Center not found.")
        request.session["active_center_id"] = membership.center_id
        return redirect("dashboard")
    return render(request, "lab/choose_center.html", {"memberships": memberships})


@center_required
def dashboard(request):
    orders = TestOrder.objects.filter(center=request.center).select_related("patient")[:8]
    context = {
        "center": request.center,
        "orders": orders,
        "patient_count": Patient.objects.filter(center=request.center).count(),
        "open_count": TestOrder.objects.filter(center=request.center)
        .exclude(status=TestOrder.Status.RELEASED)
        .count(),
        "review_count": TestOrder.objects.filter(
            center=request.center, status=TestOrder.Status.READY_FOR_REVIEW
        ).count(),
    }
    return render(request, "lab/dashboard.html", context)


@center_required
def patient_list(request):
    patients = Patient.objects.filter(center=request.center)
    return render(request, "lab/patients.html", {"patients": patients})


@roles_required(Membership.Role.CENTER_ADMIN, Membership.Role.FRONT_DESK)
def patient_create(request):
    form = PatientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        patient = form.save(commit=False)
        patient.center = request.center
        patient.save()
        record_audit(request, "patient_registered", "patient", patient.pk)
        messages.success(request, "Patient registered.")
        return redirect("patient_list")
    return render(request, "lab/patient_form.html", {"form": form})


@center_required
def order_list(request):
    orders = TestOrder.objects.filter(center=request.center).select_related("patient")
    return render(request, "lab/orders.html", {"orders": orders})


@roles_required(Membership.Role.CENTER_ADMIN, Membership.Role.FRONT_DESK)
def order_create(request):
    form = TestOrderForm(request.POST or None, center=request.center)
    if request.method == "POST" and form.is_valid():
        order = form.save(commit=False)
        order.center = request.center
        order.created_by = request.user
        order.save()
        for test in form.cleaned_data["tests"]:
            OrderTest.objects.create(order=order, test=test)
        record_audit(
            request,
            "order_created",
            "order",
            order.pk,
            order=order,
            details={"test_count": order.items.count()},
        )
        messages.success(request, f"Order {order.order_number} created.")
        return redirect("order_detail", order_id=order.pk)
    return render(request, "lab/order_create.html", {"form": form})


@center_required
def order_detail(request, order_id):
    order = get_object_or_404(
        TestOrder.objects.filter(center=request.center).select_related("patient"),
        pk=order_id,
    )
    items = order.items.select_related("test", "entered_by", "reviewed_by")
    if request.method == "POST":
        action = request.POST.get("action")
        role = request.membership.role
        if action == "collect":
            if role not in (Membership.Role.CENTER_ADMIN, Membership.Role.FRONT_DESK, Membership.Role.LAB_TECH):
                return HttpResponseForbidden("Your role cannot collect samples.")
            if order.status != TestOrder.Status.RECEIVED:
                messages.error(request, "Only newly received orders can be collected.")
            else:
                order.status = TestOrder.Status.COLLECTED
                order.save(update_fields=("status",))
                record_audit(request, "sample_collected", "order", order.pk, order=order)
                messages.success(request, "Sample collection recorded.")
        elif action == "save_results":
            if role not in (Membership.Role.CENTER_ADMIN, Membership.Role.LAB_TECH):
                return HttpResponseForbidden("Your role cannot enter results.")
            if order.status not in (TestOrder.Status.COLLECTED, TestOrder.Status.IN_PROGRESS):
                messages.error(request, "Results can only be entered after sample collection.")
            else:
                for item in items:
                    value = request.POST.get(f"result_{item.pk}", "").strip()
                    if value:
                        item.result_value = value
                        item.entered_by = request.user
                        item.entered_at = timezone.now()
                        item.save(update_fields=("result_value", "entered_by", "entered_at"))
                if items.exists() and all(item.result_value for item in items):
                    order.status = TestOrder.Status.READY_FOR_REVIEW
                else:
                    order.status = TestOrder.Status.IN_PROGRESS
                order.save(update_fields=("status",))
                record_audit(
                    request,
                    "results_saved",
                    "order",
                    order.pk,
                    order=order,
                    details={"result_count": sum(bool(item.result_value) for item in items)},
                )
                messages.success(request, "Results saved.")
        elif action == "release":
            if role not in (Membership.Role.CENTER_ADMIN, Membership.Role.REVIEWER):
                return HttpResponseForbidden("Your role cannot review and release results.")
            if order.status != TestOrder.Status.READY_FOR_REVIEW or not all(
                item.result_value for item in items
            ):
                messages.error(request, "All results must be entered before review.")
            else:
                now = timezone.now()
                for item in items:
                    item.reviewed_by = request.user
                    item.reviewed_at = now
                    item.save(update_fields=("reviewed_by", "reviewed_at"))
                order.status = TestOrder.Status.RELEASED
                order.save(update_fields=("status",))
                record_audit(
                    request,
                    "results_released",
                    "order",
                    order.pk,
                    order=order,
                    details={"result_count": items.count()},
                )
                messages.success(request, "Results reviewed and released.")
        else:
            return HttpResponseForbidden("Unsupported order action.")
        return redirect("order_detail", order_id=order.pk)
    return render(request, "lab/order_detail.html", {"order": order, "items": items})


@center_required
def order_report(request, order_id):
    order = get_object_or_404(
        TestOrder.objects.filter(center=request.center, status=TestOrder.Status.RELEASED)
        .select_related("patient", "center"),
        pk=order_id,
    )
    return render(request, "lab/report.html", {"order": order, "items": order.items.select_related("test")})
