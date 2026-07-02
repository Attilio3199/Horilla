"""
forms.py

This module contains the form classes used in the application.

Each form represents a specific functionality or data input in the
application. They are responsible for validating
and processing user input data.

Classes:
- YourForm: Represents a form for handling specific data input.

Usage:
from django import forms

class YourForm(forms.Form):
    field_name = forms.CharField()

    def clean_field_name(self):
        # Custom validation logic goes here
        pass
"""

import logging
import re
from datetime import date, datetime
from typing import Any

from django import forms
from django.contrib.auth.models import User
from django.db.models import Q
from django.forms import DateInput, TextInput
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as trans

from base.methods import eval_validate, reload_queryset
from base.models import Company
from employee.models import (
    Actiontype,
    BonusPoint,
    DisciplinaryAction,
    DutyRole,
    Employee,
    EmployeeBankDetails,
    EmployeeDutyHistory,
    EmployeeGeneralSetting,
    EmployeeNote,
    EmployeeTag,
    EmployeeWorkInformation,
    NoteFiles,
    Policy,
    PolicyMultipleFile,
)
from horilla import horilla_middlewares
from horilla_audit.models import AccountBlockUnblock

logger = logging.getLogger(__name__)
MULTISPACE_RE = re.compile(r"\s{2,}")


def normalize_whitespace(value):
    """
    Normalize user-entered whitespace by trimming ends and collapsing runs.
    """
    if not isinstance(value, str):
        return value
    return MULTISPACE_RE.sub(" ", value.strip())


def normalize_text_value(field_name, value):
    """
    Normalize whitespace and uppercase text values except email fields.
    """
    value = normalize_whitespace(value)
    if not isinstance(value, str):
        return value
    if "email" in (field_name or "").lower():
        return value
    return value.upper()


class ModelForm(forms.ModelForm):
    """
    Override of Django ModelForm to add initial styling and defaults.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        reload_queryset(self.fields)

        request = getattr(horilla_middlewares._thread_locals, "request", None)

        today = date.today()
        now = datetime.now()

        default_input_class = "oh-input w-100"
        select_class = "oh-select oh-select-2"
        checkbox_class = "oh-switch__checkbox"

        for field_name, field in self.fields.items():
            widget = field.widget
            label = _(field.label) if field.label else ""

            # Date field
            if isinstance(widget, forms.DateInput):
                field.initial = today
                widget.input_type = "date"
                widget.format = "%Y-%m-%d"
                field.input_formats = ["%Y-%m-%d"]

                existing_class = widget.attrs.get("class", default_input_class)
                widget.attrs.update(
                    {
                        "class": f"{existing_class} form-control",
                        "placeholder": label,
                    }
                )

            # Time field
            elif isinstance(widget, forms.TimeInput):
                field.initial = now.strftime("%H:%M")
                widget.input_type = "time"
                widget.format = "%H:%M"
                field.input_formats = ["%H:%M"]

                existing_class = widget.attrs.get("class", default_input_class)
                widget.attrs.update(
                    {
                        "class": f"{existing_class} form-control",
                        "placeholder": label,
                    }
                )

            # Number, Email, Text, File, URL fields
            elif isinstance(
                widget,
                (
                    forms.NumberInput,
                    forms.EmailInput,
                    forms.TextInput,
                    forms.FileInput,
                    forms.URLInput,
                ),
            ):
                existing_class = widget.attrs.get("class", default_input_class)
                widget.attrs.update(
                    {
                        "class": f"{existing_class} form-control",
                        "placeholder": _(field.label.title()) if field.label else "",
                    }
                )

            # Select fields
            elif isinstance(widget, forms.Select):
                if not isinstance(field, forms.ModelMultipleChoiceField):
                    field.empty_label = _("---Choose {label}---").format(label=label)
                existing_class = widget.attrs.get("class", select_class)
                widget.attrs.update({"class": existing_class})

            # Textarea
            elif isinstance(widget, forms.Textarea):
                existing_class = widget.attrs.get("class", default_input_class)
                widget.attrs.update(
                    {
                        "class": f"{existing_class} form-control",
                        "placeholder": label,
                        "rows": 2,
                        "cols": 40,
                    }
                )

            # Checkbox types
            elif isinstance(
                widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)
            ):
                existing_class = widget.attrs.get("class", checkbox_class)
                widget.attrs.update({"class": existing_class})

        # Set employee_id and company_id once
        if request:
            employee = getattr(request.user, "employee_get", None)
            if employee:
                if "employee_id" in self.fields and self._meta.model.__name__ not in [
                    "DisciplinaryAction"
                ]:
                    self.fields["employee_id"].initial = employee

                if "company_id" in self.fields:
                    company_field = self.fields["company_id"]
                    company = getattr(employee, "get_company", None)
                    if company:
                        queryset = company_field.queryset
                        company_field.initial = (
                            company if company in queryset else queryset.first()
                        )

    def clean(self):
        cleaned_data = super().clean()
        for field_name, value in list(cleaned_data.items()):
            cleaned_data[field_name] = normalize_text_value(field_name, value)
        return cleaned_data


class UserForm(ModelForm):
    """
    Form for User model
    """

    class Meta:
        """
        Meta class to add the additional info
        """

        fields = ("groups",)
        model = User


class UserPermissionForm(ModelForm):
    """
    Form for User model
    """

    class Meta:
        """
        Meta class to add the additional info
        """

        fields = ("groups", "user_permissions")
        model = User


class EmployeeForm(ModelForm):
    """
    Form for Employee model
    """

    account_number = forms.CharField(
        max_length=50,
        required=False,
        label=_("IBAN"),
        widget=forms.TextInput(attrs={"class": "oh-input w-100"}),
    )

    class Meta:
        """
        Meta class to add the additional info
        """

        model = Employee
        fields = (
            # --- Dati Anagrafici ---
            "badge_id",
            "employee_first_name",
            "employee_last_name",
            "employee_profile",
            "email",
            "phone",
            # Domicilio
            "domicilio_country",
            "domicilio_state",
            "domicilio_address",
            "domicilio_zip",
            "domicilio_citta",
            "docimicilio_provincia",
            # Residenza
            "residenza_country",
            "residenza_state",
            "residenza_address",
            "residenza_zip",
            "residenza_citta",
            "residenza_provincia",
            # --- Dati Personali ---
            "dob",
            "nascita_citta",
            "nascita_provincia",
            "gender",
            "codice_fiscale",
            "categoria_protetta",
            "codice_paghe",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs["autocomplete"] = "email"
        self.fields["phone"].widget.attrs["autocomplete"] = "phone"
        self.fields["domicilio_address"].widget.attrs["autocomplete"] = "address"
        self.fields["domicilio_country"].label = _("domicilio_country")
        self.fields["domicilio_state"].label = _("domicilio_state")
        self.fields["domicilio_address"].label = _("domicilio_address")
        self.fields["domicilio_zip"].label = _("domicilio_zip")
        self.fields["domicilio_citta"].label = _("domicilio_citta")
        self.fields["docimicilio_provincia"].label = _("docimicilio_provincia")
        self.fields["residenza_country"].label = _("residenza_country")
        self.fields["residenza_state"].label = _("residenza_state")
        self.fields["residenza_address"].label = _("residenza_address")
        self.fields["residenza_zip"].label = _("residenza_zip")
        self.fields["residenza_citta"].label = _("residenza_citta")
        self.fields["residenza_provincia"].label = _("residenza_provincia")
        self.fields["nascita_citta"].label = _("nascita_citta")
        self.fields["nascita_provincia"].label = _("nascita_provincia")

        # Default "Italy" for country fields on new employees
        if not self.instance or not self.instance.pk:
            self.initial = {
                "badge_id": self.get_next_badge_id(),
                "domicilio_country": "Italy",
                "residenza_country": "Italy",
            }
        else:
            # Load initial values for existing employees
            initial = {}
            if self.instance.dob is not None:
                initial["dob"] = self.instance.dob.strftime("%Y-%m-%d")
            # Pre-fill account_number from bank details
            if hasattr(self.instance, "employee_bank_details"):
                try:
                    initial["account_number"] = (
                        self.instance.employee_bank_details.account_number or ""
                    )
                except EmployeeBankDetails.DoesNotExist:
                    pass
            self.initial.update(initial)

    def save(self, commit=True):
        instance = super().save(commit=commit)
        # Save account_number to EmployeeBankDetails
        account_number = self.cleaned_data.get("account_number")
        if commit and instance.pk:
            bank_details, _created = EmployeeBankDetails.objects.get_or_create(
                employee_id=instance
            )
            bank_details.account_number = account_number or bank_details.account_number
            bank_details.save()
        return instance

    def as_p(self, *args, **kwargs):
        context = {"form": self}
        return render_to_string("employee/create_form/personal_info_as_p.html", context)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        if not email:
            return cleaned_data
        query = Employee.objects.entire().filter(email=email)
        if self.instance and self.instance.id:
            query = query.exclude(id=self.instance.id)

        existing_employee = query.first()

        if existing_employee:
            company_id = None
            if (
                hasattr(existing_employee, "employee_work_info")
                and existing_employee.employee_work_info
            ):
                company_id = existing_employee.employee_work_info.company_id

            if company_id:
                error_message = _(
                    "An Employee with this Email already exists in company {}".format(
                        company_id
                    )
                )
            else:
                error_message = _("An Employee with this Email already exists")

            raise forms.ValidationError({"email": error_message})
        return cleaned_data

    def get_next_badge_id(self):
        """
        This method is used to generate badge id
        """
        from base.context_processors import get_initial_prefix
        from employee.methods.methods import get_ordered_badge_ids

        prefix = get_initial_prefix(None)["get_initial_prefix"]
        data = get_ordered_badge_ids()
        result = []
        try:
            for sublist in data:
                for item in sublist:
                    if isinstance(item, str) and item.lower().startswith(
                        prefix.lower()
                    ):
                        # Find the index of the item in the sublist
                        index = sublist.index(item)
                        # Check if there is a next item in the sublist
                        if index + 1 < len(sublist):
                            result = sublist[index + 1]
                            result = re.findall(r"[a-zA-Z]+|\d+|[^a-zA-Z\d\s]", result)

            if result:
                prefix = []
                incremented = False
                for item in reversed(result):
                    total_letters = len(item)
                    total_zero_leads = 0
                    for letter in item:
                        if letter == "0":
                            total_zero_leads = total_zero_leads + 1
                            continue
                        break

                    if total_zero_leads:
                        item = item[total_zero_leads:]
                    if isinstance(item, list):
                        item = item[-1]
                    if not incremented and isinstance(eval_validate(str(item)), int):
                        item = int(item) + 1
                        incremented = True
                    if isinstance(item, int):
                        item = "{:0{}d}".format(item, total_letters)
                    prefix.insert(0, str(item))
                prefix = "".join(prefix)
        except Exception as e:
            logger.exception(e)
            prefix = get_initial_prefix(None)["get_initial_prefix"]
        return prefix

    def clean_badge_id(self):
        """
        This method is used to clean the badge id
        """
        badge_id = self.cleaned_data["badge_id"]
        if badge_id:
            all_employees = Employee.objects.entire()
            queryset = all_employees.filter(badge_id=badge_id).exclude(
                pk=self.instance.pk if self.instance else None
            )
            if queryset.exists():
                raise forms.ValidationError(trans("Badge ID must be unique."))
            if not re.search(r"\d", badge_id):
                raise forms.ValidationError(
                    trans("Badge ID must contain at least one digit.")
                )
        return badge_id


class EmployeeWorkInformationForm(ModelForm):
    """
    Form for EmployeeWorkInformation model
    """

    class Meta:
        """
        Meta class to add the additional info
        """

        model = EmployeeWorkInformation
        fields = "__all__"
        exclude = ("employee_id", "additional_info", "experience")

    def __init__(self, *args, disable=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs["autocomplete"] = "email"

        self.fields["job_position_id"].widget.attrs.update(
            {
                "onchange": "jobChange($(this))",
            }
        )

        for field in self.fields:
            self.fields[field].widget.attrs["placeholder"] = self.fields[field].label
            if disable:
                self.fields[field].disabled = True
        field_names = {
            "Department": "department",
            "Job Position": "job_position",
            "Job Role": "job_role",
            "Work Type": "work_type",
            "Employee Type": "employee_type",
            "Shift": "employee_shift",
        }
        urls = {
            "Department": "#dynamicDept",
            "Job Position": "#dynamicJobPosition",
            "Job Role": "#dynamicJobRole",
            "Work Type": "#dynamicWorkType",
            "Employee Type": "#dynamicEmployeeType",
            "Shift": "#dynamicShift",
        }

        for label, field in self.fields.items():
            if isinstance(field, forms.ModelChoiceField) and field.label in field_names:
                if field.label is not None:
                    field_name = field_names.get(field.label)
                    if field.queryset.model != Employee and field_name:
                        translated_label = _(field.label)
                        empty_label = _("---Choose {label}---").format(
                            label=translated_label
                        )
                        self.fields[label] = forms.ChoiceField(
                            choices=[("", empty_label)]
                            + list(field.queryset.values_list("id", f"{field_name}")),
                            required=field.required,
                            label=translated_label,
                            initial=field.initial,
                            widget=forms.Select(
                                attrs={
                                    "class": "oh-select oh-select-2",
                                    "onchange": f'onDynamicCreate(this.value,"{urls.get(field.label)}");',
                                }
                            ),
                        )
                        self.fields[label].choices += [
                            ("create", _("Create New {} ").format(translated_label))
                        ]

        self.fields["work_area_type"].label = _("Dipartimento (SEDE/NEGOZI)")
        self.fields["department_code"].label = _("Codice Reparto")
        self.fields["department_id"].label = _("Reparto")
        self.fields["store_code"].label = _("Codice Negozio")
        self.fields["store_name"].label = _("Negozio")
        self.fields["export_payslip"].label = _("Esporta Cedolino")
        self.fields["mirror_payslip"].label = _("Cedolino Speculare")
        self.fields["premi"].label = _("Premi")

        select_fields = [
            "work_area_type",
            "department_id",
            "job_position_id",
            "job_role_id",
            "shift_id",
            "work_type_id",
            "employee_type_id",
            "reporting_manager_id",
            "company_id",
        ]
        for field_name in select_fields:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs["class"] = "oh-select oh-select-2"
        self.fields["work_area_type"].widget.attrs["onchange"] = "toggleWorkAreaFieldsGlobal()"

        # Se esiste una sola azienda, nasconde il campo e lo pre-compila automaticamente
        _only_company = Company.objects.first() if Company.objects.count() == 1 else None
        if _only_company and "company_id" in self.fields:
            self.fields["company_id"].initial = _only_company
            self.fields["company_id"].required = False
            self.fields["company_id"].widget = forms.HiddenInput()

    def clean(self):
        cleaned_data = super().clean()
        if "employee_id" in self.errors:
            del self.errors["employee_id"]
        _only_company = Company.objects.first() if Company.objects.count() == 1 else None
        if _only_company:
            cleaned_data["company_id"] = _only_company
        return cleaned_data

    def as_p(self, *args, **kwargs):
        context = {"form": self}
        return render_to_string("employee/update_form/work_info_as_p.html", context)


class EmployeeWorkInformationUpdateForm(ModelForm):
    """
    Form for EmployeeWorkInformation model
    """

    class Meta:
        """
        Meta class to add the additional info
        """

        model = EmployeeWorkInformation
        fields = "__all__"
        exclude = ("employee_id",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for visible in self.visible_fields():
            widget_classes = visible.field.widget.attrs.get("class", "")
            if "oh-select" not in widget_classes and hasattr(visible.field.widget, "input_type") and visible.field.widget.input_type == "checkbox":
                visible.field.widget.attrs["class"] = widget_classes.strip()
            elif "oh-select" not in widget_classes:
                visible.field.widget.attrs["class"] = "oh-input w-100"
            visible.field.widget.attrs["placeholder"] = visible.field.label

        self.fields["work_area_type"].label = _("Dipartimento (SEDE/NEGOZI)")
        self.fields["department_code"].label = _("Codice Reparto")
        self.fields["department_id"].label = _("Reparto")
        self.fields["store_code"].label = _("Codice Negozio")
        self.fields["store_name"].label = _("Negozio")
        self.fields["export_payslip"].label = _("Esporta Cedolino")
        self.fields["mirror_payslip"].label = _("Cedolino Speculare")
        self.fields["premi"].label = _("Premi")

        self.fields["work_area_type"].widget.attrs["class"] = "oh-select oh-select-2"
        self.fields["department_id"].widget.attrs["class"] = "oh-select oh-select-2"
        self.fields["job_position_id"].widget.attrs["class"] = "oh-select oh-select-2"
        self.fields["job_role_id"].widget.attrs["class"] = "oh-select oh-select-2"
        self.fields["shift_id"].widget.attrs["class"] = "oh-select oh-select-2"
        self.fields["work_type_id"].widget.attrs["class"] = "oh-select oh-select-2"
        self.fields["employee_type_id"].widget.attrs["class"] = "oh-select oh-select-2"
        self.fields["reporting_manager_id"].widget.attrs["class"] = "oh-select oh-select-2"
        self.fields["company_id"].widget.attrs["class"] = "oh-select oh-select-2"
        self.fields["work_area_type"].widget.attrs["onchange"] = "toggleWorkAreaFieldsGlobal()"

        # Se esiste una sola azienda, nasconde il campo e lo pre-compila automaticamente
        _only_company = Company.objects.first() if Company.objects.count() == 1 else None
        if _only_company and "company_id" in self.fields:
            self.fields["company_id"].initial = _only_company
            self.fields["company_id"].required = False
            self.fields["company_id"].widget = forms.HiddenInput()

    def as_p(self, *args, **kwargs):
        context = {"form": self}
        return render_to_string("employee/update_form/work_info_as_p.html", context)


class EmployeeBankDetailsForm(ModelForm):
    """
    Form for EmployeeBankDetails model
    """

    address = forms.CharField(widget=forms.Textarea(attrs={"rows": 2, "cols": 40}))

    class Meta:
        """
        Meta class to add the additional info
        """

        model = EmployeeBankDetails
        fields = (
            "bank_name",
            "account_number",
            "branch",
            "any_other_code1",
            "address",
            "country",
            "state",
            "city",
            "any_other_code2",
        )
        exclude = ["employee_id", "is_active", "additional_info"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["address"].widget.attrs["autocomplete"] = "address"
        for visible in self.visible_fields():
            visible.field.widget.attrs["class"] = "oh-input w-100"

    def as_p(self, *args, **kwargs):
        context = {"form": self}
        return render_to_string("employee/update_form/bank_info_as_p.html", context)


class EmployeeBankDetailsUpdateForm(ModelForm):
    """
    Form for EmployeeBankDetails model
    """

    class Meta:
        """
        Meta class to add the additional info
        """

        model = EmployeeBankDetails
        fields = "__all__"
        exclude = ["employee_id", "is_active", "additional_info"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for visible in self.visible_fields():
            visible.field.widget.attrs["class"] = "oh-input w-100"
        for field in self.fields:
            self.fields[field].widget.attrs["placeholder"] = self.fields[field].label

    def as_p(self, *args, **kwargs):
        context = {"form": self}
        return render_to_string("employee/update_form/bank_info_as_p.html", context)


class EmployeeDutyHistoryForm(ModelForm):
    new_duty = forms.CharField(required=False, widget=forms.HiddenInput())
    duty_role_id = forms.ChoiceField(label=trans("Mansione"))

    class Meta:
        model = EmployeeDutyHistory
        fields = ("duty_role_id", "start_date", "end_date")

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        duty_choices = [("", _("---Choose Mansione---"))]
        duty_choices += [
            (str(role.id), role.title)
            for role in DutyRole.objects.all().order_by("title")
        ]
        if self.user and self.user.is_superuser:
            duty_choices.append(("create", _("+ Aggiungi Mansione")))

        self.fields["duty_role_id"].choices = duty_choices
        self.fields["start_date"].label = trans("DataInizioMansione")
        self.fields["end_date"].label = trans("DataFineMansione")

        self.fields["duty_role_id"].widget.attrs["class"] = "oh-select oh-select-2"
        self.fields["new_duty"].widget.attrs["class"] = "oh-input w-100"

    def clean(self):
        cleaned_data = super().clean()
        duty_role_value = (cleaned_data.get("duty_role_id") or "").strip()
        new_duty = (cleaned_data.get("new_duty") or "").strip()

        if not duty_role_value:
            raise forms.ValidationError(_("Select a mansione."))

        if duty_role_value == "create":
            if not (self.user and self.user.is_superuser):
                raise forms.ValidationError(_("Only superuser can add a new mansione."))
            if not new_duty:
                raise forms.ValidationError(
                    _("Enter a mansione name to create a new enum value.")
                )
            duty_role, _ = DutyRole.objects.get_or_create(title=new_duty)
            cleaned_data["duty_role_id"] = duty_role
            return cleaned_data

        duty_role = DutyRole.objects.filter(id=duty_role_value).first()
        if not duty_role:
            raise forms.ValidationError(_("Invalid mansione selected."))

        cleaned_data["duty_role_id"] = duty_role

        return cleaned_data


excel_columns = [
    ("id", trans("Employee ID")),
    ("badge_id", trans("Badge ID")),
    ("employee_user_id", trans("User")),
    ("employee_first_name", trans("First Name")),
    ("employee_last_name", trans("Last Name")),
    ("employee_profile", trans("Profile Image")),
    ("email", trans("Email")),
    ("phone", trans("Phone")),
    ("experience", trans("Experience")),
    ("gender", trans("Gender")),
    ("dob", trans("Date of Birth")),
    ("domicilio_country", trans("domicilio_country")),
    ("domicilio_state", trans("domicilio_state")),
    ("domicilio_address", trans("domicilio_address")),
    ("domicilio_zip", trans("domicilio_zip")),
    ("domicilio_citta", trans("domicilio_citta")),
    ("docimicilio_provincia", trans("docimicilio_provincia")),
    ("residenza_country", trans("residenza_country")),
    ("residenza_state", trans("residenza_state")),
    ("residenza_address", trans("residenza_address")),
    ("residenza_zip", trans("residenza_zip")),
    ("residenza_citta", trans("residenza_citta")),
    ("residenza_provincia", trans("residenza_provincia")),
    ("nascita_citta", trans("nascita_citta")),
    ("nascita_provincia", trans("nascita_provincia")),
    ("codice_fiscale", trans("Codice Fiscale")),
    ("categoria_protetta", trans("Categoria Protetta")),
    ("codice_paghe", trans("Codice Paghe")),
    ("qualification", trans("Qualification")),
    ("marital_status", trans("Marital Status")),
    ("children", trans("Children")),
    ("is_active", trans("Is active")),
    ("additional_info", trans("Additional Info")),
    ("is_from_onboarding", trans("Is From Onboarding")),
    ("is_directly_converted", trans("Is Directly Converted")),
    ("emergency_contact", trans("Emergency Contact")),
    ("emergency_contact_name", trans("Emergency Contact Name")),
    ("emergency_contact_relation", trans("Emergency Contact Relation")),
    ("employee_work_info__email", trans("Work Email")),
    ("employee_work_info__mobile", trans("Work Phone")),
    ("employee_work_info__department_id", trans("Department")),
    ("employee_work_info__job_position_id", trans("Job Position")),
    ("employee_work_info__job_role_id", trans("Job Role")),
    ("employee_work_info__shift_id", trans("Shift")),
    ("employee_work_info__work_type_id", trans("Work Type")),
    ("employee_work_info__reporting_manager_id", trans("Reporting Manager")),
    ("employee_work_info__employee_type_id", trans("Employee Type")),
    ("employee_work_info__work_area_type", trans("Dipartimento (SEDE/NEGOZI)")),
    ("employee_work_info__department_code", trans("Codice Reparto")),
    ("employee_work_info__store_code", trans("Codice Negozio")),
    ("employee_work_info__store_name", trans("Negozio")),
    ("employee_work_info__location", trans("Location")),
    ("employee_work_info__date_joining", trans("Date Joining")),
    ("employee_work_info__basic_salary", trans("Basic Salary")),
    ("employee_work_info__salary_hour", trans("Salary Hour")),
    ("employee_work_info__contract_end_date", trans("Contract End Date")),
    ("employee_work_info__company_id", trans("Company")),
    ("employee_work_info__export_payslip", trans("Esporta Cedolino")),
    ("employee_work_info__mirror_payslip", trans("Cedolino Speculare")),
    ("employee_work_info__premi", trans("Premi")),
    ("employee_bank_details__bank_name", trans("Bank Name")),
    ("employee_bank_details__branch", trans("Branch")),
    ("employee_bank_details__account_number", trans("IBAN")),
    ("employee_bank_details__any_other_code1", trans("Bank Code #1")),
    ("employee_bank_details__any_other_code2", trans("Bank Code #2")),
    ("employee_bank_details__country", trans("Bank Country")),
    ("employee_bank_details__state", trans("Bank State")),
    ("employee_bank_details__city", trans("Bank City")),
]
fields_to_remove = [
    "badge_id",
    "employee_first_name",
    "employee_last_name",
    "is_active",
    "email",
    "phone",
    "employee_bank_details__account_number",
]


class EmployeeExportExcelForm(forms.Form):
    selected_fields = forms.MultipleChoiceField(
        choices=excel_columns,
        widget=forms.CheckboxSelectMultiple,
        initial=[
            "badge_id",
            "employee_first_name",
            "employee_last_name",
            "email",
            "phone",
            "gender",
            "employee_work_info__department_id",
            "employee_work_info__job_position_id",
            "employee_work_info__job_role_id",
            "employee_work_info__shift_id",
            "employee_work_info__work_type_id",
            "employee_work_info__reporting_manager_id",
            "employee_work_info__employee_type_id",
            "employee_work_info__work_area_type",
            "employee_work_info__department_code",
            "employee_work_info__store_code",
            "employee_work_info__store_name",
            "employee_work_info__location",
            "employee_work_info__date_joining",
            "employee_work_info__basic_salary",
            "employee_work_info__salary_hour",
            "employee_work_info__contract_end_date",
            "employee_work_info__company_id",
            "employee_work_info__export_payslip",
            "employee_work_info__mirror_payslip",
            "employee_work_info__premi",
        ],
    )


class BulkUpdateFieldForm(forms.Form):
    update_fields = forms.MultipleChoiceField(
        choices=excel_columns, label=_("Select Fields to Update")
    )
    bulk_employee_ids = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        updated_choices = [
            (value, label)
            for value, label in self.fields["update_fields"].choices
            if value not in fields_to_remove
        ]
        self.fields["update_fields"].choices = updated_choices
        for visible in self.visible_fields():
            visible.field.widget.attrs["class"] = "oh-select oh-select-2 oh-input w-100"


class EmployeeNoteForm(ModelForm):
    """
    Form for EmployeeNote model
    """

    class Meta:
        """
        Meta class to add the additional info
        """

        model = EmployeeNote
        fields = ("description",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["note_files"] = MultipleFileField(label="files")
        self.fields["note_files"].required = False

    def save(self, commit: bool = ...) -> Any:
        attachement = []
        multiple_attachment_ids = []
        attachements = None
        if self.files.getlist("note_files"):
            attachements = self.files.getlist("note_files")
            self.instance.attachement = attachements[0]
            multiple_attachment_ids = []

            for attachement in attachements:
                file_instance = NoteFiles()
                file_instance.files = attachement
                file_instance.save()
                multiple_attachment_ids.append(file_instance.pk)
        instance = super().save(commit)
        if commit:
            instance.note_files.add(*multiple_attachment_ids)
        return instance, multiple_attachment_ids


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = [single_file_clean(data, initial)]
        if len(result) == 0:
            result = [[]]
        return result[0]


class PolicyForm(ModelForm):
    """
    PolicyForm
    """

    class Meta:
        model = Policy
        fields = "__all__"
        exclude = ["attachments", "is_active"]
        widgets = {
            "body": forms.Textarea(
                attrs={"data-summernote": "", "style": "display:none;"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attachment"] = MultipleFileField(
            label=trans("Attachments"), required=False
        )

    def save(self, *args, commit=True, **kwargs):
        attachemnt = []
        multiple_attachment_ids = []
        attachemnts = None
        if self.files.getlist("attachment"):
            attachemnts = self.files.getlist("attachment")
            multiple_attachment_ids = []
            for attachemnt in attachemnts:
                file_instance = PolicyMultipleFile()
                file_instance.attachment = attachemnt
                file_instance.save()
                multiple_attachment_ids.append(file_instance.pk)
        instance = super().save(commit)
        if commit:
            instance.attachments.add(*multiple_attachment_ids)
        return instance, attachemnts


class BonusPointAddForm(ModelForm):
    class Meta:
        model = BonusPoint
        fields = ["points", "reason"]
        widgets = {
            "reason": forms.TextInput(attrs={"required": "required"}),
        }


class BonusPointRedeemForm(ModelForm):
    class Meta:
        model = BonusPoint
        fields = ["points"]

    def clean(self):
        cleaned_data = super().clean()
        available_points = BonusPoint.objects.filter(
            employee_id=self.instance.employee_id
        ).first()
        if not available_points or available_points.points < cleaned_data["points"]:
            raise forms.ValidationError({"points": "Not enough bonus points to redeem"})
        if cleaned_data["points"] <= 0:
            raise forms.ValidationError(
                {"points": "Points must be greater than zero to redeem."}
            )


class DisciplinaryActionForm(ModelForm):
    class Meta:
        model = DisciplinaryAction
        fields = "__all__"
        exclude = ["objects", "is_active"]

    action = forms.ModelChoiceField(
        queryset=Actiontype.objects.all(),
        label=_("Action"),
        widget=forms.Select(
            attrs={
                "class": "oh-select oh-select-2",
                "onchange": "actionTypeChange($(this))",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        action_choices = [("", _("---Choose Action---"))] + list(
            self.fields["action"].queryset.values_list("id", "title")
        )
        self.fields["action"].choices = action_choices
        if self.instance.pk is None:
            self.fields["action"].choices += [("create", _("Create new action type "))]

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html


class ActiontypeForm(ModelForm):
    class Meta:
        model = Actiontype
        fields = "__all__"
        exclude = ["is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["action_type"].widget.attrs.update(
            {
                "onchange": "actionChange($(this))",
            }
        )


class EmployeeTagForm(ModelForm):
    """
    Employee Tags form
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = EmployeeTag
        fields = "__all__"
        exclude = ["is_active"]
        widgets = {"color": TextInput(attrs={"type": "color", "style": "height:50px"})}


class EmployeeGeneralSettingPrefixForm(forms.ModelForm):

    class Meta:

        model = EmployeeGeneralSetting
        exclude = ["objects"]
        widgets = {
            "badge_id_prefix": forms.TextInput(attrs={"class": "oh-input w-100"}),
            "company_id": forms.Select(attrs={"class": "oh-select oh-select-2 w-100"}),
        }
