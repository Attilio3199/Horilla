from django import forms
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from base.forms import ModelForm
from base.methods import reload_queryset
from employee.filters import EmployeeFilter
from employee.models import Employee
from employee.models import EmployeeWorkInformation
from horilla_documents.models import (
    Document,
    DocumentCategory,
    DocumentRequest,
    DocumentSubCategory,
    Maternita,
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


class MaterniaForm(forms.ModelForm):
    """Form per creare/modificare una riga Maternita"""

    # Campo select dipendente sostituta — popola sostituta (str) e id_sostituta (badge_id)
    sostituta_employee = forms.ModelChoiceField(
        queryset=Employee.objects.all(),
        required=False,
        label=_("Sostituta"),
        widget=forms.Select(attrs={"class": "oh-input w-100"}),
    )

    class Meta:
        model = Maternita
        fields = [
            "employee_id",
            "n_figlio",
            "nome_figlio",
            "data_comunicazione",
            "data_prevista_parto",
            "sedia_maternita",
            "data_nascita",
            "data_rientro",
            "negozio",
            "documento",
        ]
        widgets = {
            "employee_id": forms.HiddenInput(),
            "n_figlio": forms.NumberInput(attrs={"class": "oh-input w-100"}),
            "nome_figlio": forms.TextInput(attrs={"class": "oh-input w-100"}),
            "data_comunicazione": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "oh-input w-100"}
            ),
            "data_prevista_parto": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "oh-input w-100"}
            ),
            "sedia_maternita": forms.Select(attrs={"class": "oh-input w-100"}),
            "data_nascita": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "oh-input w-100"}
            ),
            "data_rientro": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "oh-input w-100"}
            ),
            "negozio": forms.Select(attrs={"class": "oh-input w-100"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Scelte negozio: store_name da NEGOZI
        store_names = (
            EmployeeWorkInformation.objects.filter(work_area_type="NEGOZI")
            .exclude(store_name__isnull=True)
            .exclude(store_name="")
            .values_list("store_name", flat=True)
            .distinct()
            .order_by("store_name")
        )
        negozio_choices = [("" , "---------")] + [(s, s) for s in store_names]
        self.fields["negozio"] = forms.ChoiceField(
            choices=negozio_choices,
            required=False,
            label=_("Negozio"),
            widget=forms.Select(attrs={"class": "oh-input w-100"}),
        )
        # n_figlio: auto-calcola il valore di default se nuovo record
        if not self.instance.pk and "employee_id" in self.data:
            try:
                emp_id = int(self.data["employee_id"])
                count = Maternita.objects.filter(employee_id_id=emp_id).count()
                self.fields["n_figlio"].initial = count + 1
            except (ValueError, TypeError):
                pass

    def clean(self):
        cleaned = super().clean()
        emp_sel = cleaned.get("sostituta_employee")
        if emp_sel:
            cleaned["sostituta"] = f"{emp_sel.employee_last_name} {emp_sel.employee_first_name}"
            cleaned["id_sostituta"] = emp_sel.badge_id or ""
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        cleaned = self.cleaned_data
        if cleaned.get("sostituta_employee"):
            instance.sostituta = cleaned["sostituta"]
            instance.id_sostituta = cleaned["id_sostituta"]
        if commit:
            instance.save()
        return instance


class DocumentForm(ModelForm):
    """form to create a new Document"""

    class Meta:
        model = Document
        fields = "__all__"
        exclude = [
            "title", "document_request_id", "status", "reject_reason", "is_active",
            "upload_date", "notify_before", "is_digital_asset",
            "maternita",  # gestita manualmente nella view
        ]
        widgets = {
            "employee_id": forms.HiddenInput(),
            "document_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input w-100"}
            ),
            "beneficiario": forms.TextInput(
                attrs={"class": "oh-input w-100", "placeholder": _("Beneficiario")}
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
        emp_id = None
        if self.instance and self.instance.pk:
            emp_id = self.instance.employee_id_id
        elif "employee_id" in self.data:
            try:
                emp_id = int(self.data["employee_id"])
            except (ValueError, TypeError):
                pass
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
            "reject_reason",
            "is_active",
            "created_by",
            "modified_by",
            "employee_id",
            "upload_date",
            "notify_before",
            "is_digital_asset",
            "beneficiario",
            "maternita",
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
