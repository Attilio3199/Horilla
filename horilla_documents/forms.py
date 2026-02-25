from django import forms
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from base.forms import ModelForm
from base.methods import reload_queryset
from employee.filters import EmployeeFilter
from employee.models import Employee
from horilla_documents.models import (
    Document,
    DocumentCategory,
    DocumentRequest,
    DocumentSubCategory,
)
from horilla_widgets.widgets.horilla_multi_select_field import HorillaMultiSelectField
from horilla_widgets.widgets.select_widgets import HorillaMultiSelectWidget


class DocumentCategoryForm(forms.ModelForm):
    class Meta:
        model = DocumentCategory
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={"class": "oh-input w-100", "placeholder": _("Nome categoria")})}


class DocumentSubCategoryForm(forms.ModelForm):
    class Meta:
        model = DocumentSubCategory
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={"class": "oh-input w-100", "placeholder": _("Nome sottocategoria")})}


class DocumentRequestForm(ModelForm):
    """form to create a new Document Request"""

    class Meta:
        model = DocumentRequest
        fields = "__all__"
        exclude = ["is_active"]

    def clean(self):
        cleaned_data = super().clean()
        if isinstance(self.fields["employee_id"], HorillaMultiSelectField):
            self.errors.pop("employee_id", None)
            if len(self.data.getlist("employee_id")) < 1:
                raise forms.ValidationError({"employee_id": "This field is required"})

            employee_data = self.fields["employee_id"].queryset.filter(
                id__in=self.data.getlist("employee_id")
            )
            cleaned_data["employee_id"] = employee_data

        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee_id"] = HorillaMultiSelectField(
            queryset=Employee.objects.all(),
            widget=HorillaMultiSelectWidget(
                filter_route_name="employee-widget-filter",
                filter_class=EmployeeFilter,
                filter_instance_contex_name="f",
                filter_template_path="employee_filters.html",
                required=True,
                instance=self.instance,
            ),
            label=_("Employee"),
        )
        reload_queryset(self.fields)


class DocumentForm(ModelForm):
    """form to create a new Document"""

    class Meta:
        model = Document
        fields = "__all__"
        exclude = ["title", "document_request_id", "status", "reject_reason", "is_active", "upload_date"]
        widgets = {
            "employee_id": forms.HiddenInput(),
            "document_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input w-100"}
            ),
            "start_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input w-100"}
            ),
            "expiry_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input w-100"}
            ),
            "notes": forms.Textarea(
                attrs={"class": "oh-input w-100", "rows": 3, "placeholder": _("Note aggiuntive...")}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].required = True
        self.fields["subcategory"].required = False
        self.fields["subcategory"].queryset = DocumentSubCategory.objects.none()
        # If editing, populate subcategory choices for the current category
        if self.instance and self.instance.pk and self.instance.category_id:
            self.fields["subcategory"].queryset = DocumentSubCategory.objects.filter(
                category_id=self.instance.category_id
            )
        elif "category" in self.data:
            try:
                cat_id = int(self.data.get("category"))
                self.fields["subcategory"].queryset = DocumentSubCategory.objects.filter(category_id=cat_id)
            except (ValueError, TypeError):
                pass

    def as_p(self):
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html


class DocumentUpdateForm(ModelForm):
    """form to Update a Document (fulfil a request)"""

    class Meta:
        model = Document
        fields = "__all__"
        exclude = [
            "title",
            "document_request_id",
            "status",
            "created_by",
            "modified_by",
            "employee_id",
            "upload_date",
        ]
        widgets = {
            "document_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input w-100"}
            ),
            "start_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input w-100"}
            ),
            "expiry_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input w-100"}
            ),
            "notes": forms.Textarea(
                attrs={"class": "oh-input w-100", "rows": 3, "placeholder": _("Note aggiuntive...")}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].required = True
        self.fields["subcategory"].required = False
        self.fields["subcategory"].queryset = DocumentSubCategory.objects.none()
        if self.instance and self.instance.pk and self.instance.category_id:
            self.fields["subcategory"].queryset = DocumentSubCategory.objects.filter(
                category_id=self.instance.category_id
            )
        elif "category" in self.data:
            try:
                cat_id = int(self.data.get("category"))
                self.fields["subcategory"].queryset = DocumentSubCategory.objects.filter(category_id=cat_id)
            except (ValueError, TypeError):
                pass


class DocumentRejectForm(ModelForm):
    verbose_name = Document()._meta.get_field("reject_reason").verbose_name

    class Meta:
        model = Document
        fields = ["reject_reason"]
