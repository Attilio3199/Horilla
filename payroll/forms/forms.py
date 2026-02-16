"""
forms.py
"""

from typing import Any

from django import forms
from django.forms import widgets
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from base.forms import Form, ModelForm
from employee.forms import MultipleFileField
from employee.models import Employee
from payroll.context_processors import get_active_employees
from payroll.models.models import (
    Contract,
    EncashmentGeneralSettings,
    PayrollGeneralSetting,
    ReimbursementFile,
    ReimbursementrequestComment,
)


DATE_INPUT_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"]


class ContractForm(ModelForm):
    """
    ContactForm
    """

    verbose_name = _("Contract")
    contract_start_date = forms.DateField(
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.DateInput(
            format="%d/%m/%Y",
            attrs={"type": "text", "placeholder": "DD/MM/YYYY"},
        ),
    )
    contract_end_date = forms.DateField(
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.DateInput(
            format="%d/%m/%Y",
            attrs={"type": "text", "placeholder": "DD/MM/YYYY"},
        ),
    )

    class Meta:
        """
        Meta class for additional options
        """

        fields = [
            "employee_id",
            "contract_name",
            "contract_status",
            "tipo_contratto",
            "contract_start_date",
            "contract_end_date",
            "lun",
            "mar",
            "mer",
            "gio",
            "ven",
            "sab",
            "dom",
        ]
        model = Contract

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee_id"].widget.attrs.update(
            {"onchange": "contractInitial(this)"}
        )
        self.fields["contract_status"].widget.attrs.update(
            {
                "class": "oh-select",
            }
        )
        self.fields["contract_name"].required = False
        self.fields["contract_name"].label = _("Nota Contratto")
        self.fields["contract_name"].widget = forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": _("Inserisci una Nota Contratto"),
            }
        )
        
        self.fields["contract_start_date"].input_formats = DATE_INPUT_FORMATS
        self.fields["contract_end_date"].input_formats = DATE_INPUT_FORMATS
        self.fields["contract_start_date"].widget.format = "%d/%m/%Y"
        self.fields["contract_end_date"].widget.format = "%d/%m/%Y"
        self.fields["contract_start_date"].widget.input_type = "text"
        self.fields["contract_end_date"].widget.input_type = "text"
        self.fields["contract_start_date"].widget.attrs.update(
            {"placeholder": "DD/MM/YYYY", "autocomplete": "off"}
        )
        self.fields["contract_end_date"].widget.attrs.update(
            {"placeholder": "DD/MM/YYYY", "autocomplete": "off"}
        )

        if self.instance and self.instance.contract_start_date:
            self.initial["contract_start_date"] = self.instance.contract_start_date.strftime(
                "%d/%m/%Y"
            )
        if self.instance and self.instance.contract_end_date:
            self.initial["contract_end_date"] = self.instance.contract_end_date.strftime(
                "%d/%m/%Y"
            )
        
        # Add select class for tipo_contratto dropdown
        if "tipo_contratto" in self.fields:
            self.fields["tipo_contratto"].widget.attrs.update({"class": "oh-select"})
        
        if self.instance and self.instance.pk:
            dynamic_url = self.get_dynamic_hx_post_url(self.instance)
            self.fields["contract_status"].widget.attrs.update(
                {
                    "hx-target": "this",
                    "hx-post": dynamic_url,
                    "hx-swap": "beforebegin",
                }
            )
        first = PayrollGeneralSetting.objects.first()
        if first and self.instance.pk is None:
            self.initial["notice_period_in_days"] = first.notice_period
        if "contract_document" in self.fields:
            self.fields["contract_document"].widget.attrs[
                "accept"
            ] = ".jpg, .jpeg, .png, .pdf"

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("contract_form.html", context)
        return table_html

    def get_dynamic_hx_post_url(self, instance):
        """
        Render the url for contract status update through hx request
        """
        return f"/payroll/update-contract-status/{instance.pk}"


class ReimbursementRequestCommentForm(ModelForm):
    """
    ReimbursementRequestCommentForm form
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = ReimbursementrequestComment
        fields = ("comment",)


class reimbursementCommentForm(ModelForm):
    """
    Reimbursement request comment model form
    """

    verbose_name = "Add Comment"

    class Meta:
        """
        Meta class for additional options
        """

        model = ReimbursementrequestComment
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["files"] = MultipleFileField(label="files")
        self.fields["files"].required = False
        self.fields["files"].widget.attrs["accept"] = ".jpg, .jpeg, .png, .pdf"

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def save(self, commit: bool = ...) -> Any:
        multiple_files_ids = []
        files = None
        if self.files.getlist("files"):
            files = self.files.getlist("files")
            self.instance.attachemnt = files[0]
            multiple_files_ids = []
            for attachemnt in files:
                file_instance = ReimbursementFile()
                file_instance.file = attachemnt
                file_instance.save()
                multiple_files_ids.append(file_instance.pk)
        instance = super().save(commit)
        if commit:
            instance.files.add(*multiple_files_ids)
        return instance, files


class EncashmentGeneralSettingsForm(ModelForm):
    class Meta:
        model = EncashmentGeneralSettings
        fields = "__all__"


class DashboardExport(Form):
    status_choices = [
        ("", ""),
        ("draft", "Draft"),
        ("review_ongoing", "Review Ongoing"),
        ("confirmed", "Confirmed"),
        ("paid", "Paid"),
    ]
    start_date = forms.DateField(
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.DateInput(
            format="%d/%m/%Y",
            attrs={
                "type": "text",
                "class": "oh-input w-100",
                "placeholder": "DD/MM/YYYY",
                "autocomplete": "off",
            },
        ),
    )
    end_date = forms.DateField(
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.DateInput(
            format="%d/%m/%Y",
            attrs={
                "type": "text",
                "class": "oh-input w-100",
                "placeholder": "DD/MM/YYYY",
                "autocomplete": "off",
            },
        ),
    )
    employees = forms.ChoiceField(
        required=False,
        choices=[(emp.id, emp.get_full_name()) for emp in Employee.objects.all()],
        widget=forms.SelectMultiple,
    )
    status = forms.ChoiceField(required=False, choices=status_choices)
    contributions = forms.ChoiceField(
        required=False,
        choices=[
            (emp.id, emp.get_full_name())
            for emp in get_active_employees(None)["get_active_employees"]
        ],
        widget=forms.SelectMultiple,
    )
