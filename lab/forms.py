from django import forms

from .models import Patient, TestCatalog, TestOrder


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ("full_name", "date_of_birth", "sex", "phone")
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
        }


class TestOrderForm(forms.ModelForm):
    tests = forms.ModelMultipleChoiceField(
        queryset=TestCatalog.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = TestOrder
        fields = ("patient", "tests", "notes")

    def __init__(self, *args, center, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["patient"].queryset = Patient.objects.filter(center=center)
        self.fields["tests"].queryset = TestCatalog.objects.filter(center=center, is_active=True)
