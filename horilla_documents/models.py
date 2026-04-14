import os
from datetime import date

from django.apps import apps
from django.db import models
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from django.forms import ValidationError
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _

from base.horilla_company_manager import HorillaCompanyManager
from employee.models import Employee
from horilla.models import HorillaModel


def document_upload_path(instance, filename):
    """
    Saves documents in a folder tree based on category/subcategory and
    renames the file using the convention:
        nomecognome_categoria_datainizio_datacaricamento.ext
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"

    # ── Employee name ──────────────────────────────────────────────────────
    employee = instance.employee_id  # ForeignKey → Employee object
    if employee:
        first = slugify(employee.employee_first_name or "")
        last = slugify(employee.employee_last_name or "")
        emp_name = f"{first}{last}" if (first or last) else "dipendente"
    else:
        emp_name = "dipendente"

    # ── Category ───────────────────────────────────────────────────────────
    category_name = instance.category.name if instance.category else "senza_categoria"
    category_slug = slugify(category_name)

    # ── Subcategory ────────────────────────────────────────────────────────
    subcategory_name = instance.subcategory.name if instance.subcategory else None
    subcategory_slug = slugify(subcategory_name) if subcategory_name else None

    # ── Dates ──────────────────────────────────────────────────────────────
    start = (
        instance.start_date.strftime("%d%m%Y") if instance.start_date else "nodatainizio"
    )
    today = timezone.now().strftime("%d%m%Y")

    # ── Final filename & folder ────────────────────────────────────────────
    new_filename = f"{emp_name}_{category_slug}_{start}_{today}.{ext}"

    if subcategory_slug:
        folder = f"documents/{category_slug}/{subcategory_slug}"
    else:
        folder = f"documents/{category_slug}"

    return f"{folder}/{new_filename}"


class DocumentCategory(HorillaModel):
    """Category for documents (e.g. Contratto, Documento identità)"""

    name = models.CharField(max_length=200, unique=True, verbose_name=_("Category"))

    class Meta:
        verbose_name = _("Document Category")
        verbose_name_plural = _("Document Categories")
        ordering = ["name"]

    def __str__(self):
        return self.name


class DocumentSubCategory(HorillaModel):
    """Sub-category for documents, filtered by parent category"""

    name = models.CharField(max_length=200, verbose_name=_("Sub Category"))
    category = models.ForeignKey(
        DocumentCategory,
        on_delete=models.CASCADE,
        related_name="subcategories",
        verbose_name=_("Category"),
    )

    class Meta:
        verbose_name = _("Document Sub Category")
        verbose_name_plural = _("Document Sub Categories")
        ordering = ["name"]
        unique_together = [["name", "category"]]

    def __str__(self):
        return self.name

STATUS = [
    ("requested", _("Requested")),
    ("approved", _("Approved")),
    ("rejected", _("Rejected")),
]
FORMATS = [
    ("any", "Any"),
    ("pdf", "PDF"),
    ("txt", "TXT"),
    ("docx", "DOCX"),
    ("xlsx", "XLSX"),
    ("jpg", "JPG"),
    ("png", "PNG"),
    ("jpeg", "JPEG"),
]

SEDIA_MATERNITA_CHOICES = [
    ("SI", "Sì"),
    ("NO", "No"),
]


def maternita_upload_path(instance, filename):
    """Salva i file della maternità in media/documents/maternita/comunicazioni/"""
    return f"documents/maternita/comunicazioni/{filename}"


def document_create(instance):
    employees = instance.employee_id.all()
    for employee in employees:
        document = Document.objects.get_or_create(
            employee_id=employee,
            document_request_id=instance,
            defaults={"title": f"Upload {instance.title}"},
        )
        document[0].title = f"Upload {instance.title}"
        document[0].save()


class DocumentRequest(HorillaModel):
    title = models.CharField(max_length=100, verbose_name=_("Title"))
    employee_id = models.ManyToManyField(Employee, verbose_name=_("Employees"))
    format = models.CharField(choices=FORMATS, max_length=10, verbose_name=_("Format"))
    max_size = models.IntegerField(
        blank=True, null=True, verbose_name=_("Max size (In MB)")
    )
    description = models.TextField(
        blank=True, null=True, max_length=255, verbose_name=_("Description")
    )
    objects = HorillaCompanyManager(
        related_company_field="employee_id__employee_work_info__company_id"
    )

    class Meta:
        verbose_name = _("Document Request")
        verbose_name_plural = _("Document Requests")

    def __str__(self):
        return self.title


@receiver(m2m_changed, sender=DocumentRequest.employee_id.through)
def document_request_m2m_changed(sender, instance, action, **kwargs):
    if action == "post_add":
        document_create(instance)
    elif action == "post_remove":
        document_create(instance)


class Maternita(HorillaModel):
    """
    Rappresenta una gravidanza/maternità di un dipendente.
    Una riga = un figlio.  A questa riga possono essere collegati più
    Document (categoria "MATERNITA'") tramite Document.maternita FK.
    """

    employee_id = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        verbose_name=_("Dipendente"),
        related_name="maternita_set",
    )
    n_figlio = models.IntegerField(verbose_name=_("N° Figlio"))
    nome_figlio = models.CharField(
        max_length=255, null=True, blank=True, verbose_name=_("Nome Figlio")
    )
    data_comunicazione = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Data Comunicazione")
    )
    data_prevista_parto = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Data Prevista Parto")
    )
    sedia_maternita = models.CharField(
        max_length=10,
        choices=SEDIA_MATERNITA_CHOICES,
        null=True,
        blank=True,
        verbose_name=_("Sedia Maternità"),
    )
    # Sostituta: testo storicizzato (cognome + nome) + badge_id al momento dell'inserimento
    sostituta = models.CharField(
        max_length=255, null=True, blank=True, verbose_name=_("Sostituta")
    )
    id_sostituta = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name=_("Badge ID Sostituta"),
        help_text=_("badge_id del dipendente selezionato come sostituta"),
    )
    data_nascita = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Data Nascita")
    )
    data_rientro = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Data Rientro")
    )
    negozio = models.CharField(
        max_length=255, null=True, blank=True, verbose_name=_("Negozio")
    )
    documento = models.FileField(
        upload_to=maternita_upload_path,
        null=True,
        blank=True,
        verbose_name=_("Documento comunicazione"),
    )
    note = models.TextField(
        null=True, blank=True, verbose_name=_("Note")
    )

    class Meta:
        verbose_name = _("Maternità")
        verbose_name_plural = _("Maternità")
        unique_together = [["employee_id", "n_figlio"]]
        ordering = ["employee_id", "n_figlio"]

    def __str__(self):
        emp = str(self.employee_id)
        return f"{emp} — figlio n°{self.n_figlio}"

    def save(self, *args, **kwargs):
        # Auto-calcola n_figlio se non impostato
        if not self.pk and not self.n_figlio:
            existing = Maternita.objects.filter(
                employee_id=self.employee_id
            ).count()
            self.n_figlio = existing + 1
        super().save(*args, **kwargs)


class Document(HorillaModel):
    title = models.CharField(max_length=250, blank=True, null=True)
    category = models.ForeignKey(
        DocumentCategory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Categoria"),
    )
    subcategory = models.ForeignKey(
        DocumentSubCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Sottocategoria"),
    )
    employee_id = models.ForeignKey(
        Employee, on_delete=models.PROTECT, verbose_name=_("Employee")
    )
    document_request_id = models.ForeignKey(
        DocumentRequest, on_delete=models.PROTECT, null=True, blank=True
    )
    document = models.FileField(
        upload_to=document_upload_path, null=True, blank=True, verbose_name=_("Document")
    )
    status = models.CharField(
        choices=STATUS, max_length=10, default="requested", verbose_name=_("Status")
    )
    reject_reason = models.TextField(
        blank=True, null=True, max_length=255, verbose_name=_("Reject Reason")
    )
    document_date = models.DateField(null=True, blank=True, verbose_name=_("Data Documento"))
    start_date = models.DateField(null=True, blank=True, verbose_name=_("Data Inizio"))
    expiry_date = models.DateField(null=True, blank=True, verbose_name=_("Data Fine"))
    upload_date = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Data Caricamento")
    )
    notes = models.TextField(null=True, blank=True, verbose_name=_("Note"))
    notify_before = models.IntegerField(
        default=1, null=True, verbose_name=_("Notifica Prima (giorni)")
    )
    # ── Campi specifici per categoria "104" ────────────────────────────────
    beneficiario = models.CharField(
        max_length=255, null=True, blank=True, verbose_name=_("Beneficiario")
    )
    # ── Collegamento a Maternità (popolato solo se categoria = "MATERNITA'") ──
    maternita = models.ForeignKey(
        "Maternita",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
        verbose_name=_("Maternità"),
    )
    is_digital_asset = models.BooleanField(
        default=False, verbose_name=_("Is Digital Asset")
    )
    objects = HorillaCompanyManager(
        related_company_field="employee_id__employee_work_info__company_id"
    )

    class Meta:
        verbose_name = _("Document")
        verbose_name_plural = _("Documents")

    def __str__(self) -> str:
        if self.category:
            return str(self.category)
        return self.title or f"Document {self.pk}"

    def clean(self, *args, **kwargs):
        super().clean(*args, **kwargs)
        file = self.document

        if file and self.document_request_id:
            fmt = self.document_request_id.format
            max_size = self.document_request_id.max_size
            if max_size:
                if file.size > max_size * 1024 * 1024:
                    raise ValidationError(
                        {"document": _("File size exceeds the limit")}
                    )
            ext = file.name.split(".")[-1].lower()
            if fmt != "any" and ext != fmt:
                raise ValidationError(
                    {"document": _("Please upload {} file only.").format(fmt)}
                )

    def save(self, *args, **kwargs):
        # Auto-set title from category for backward compat
        if not self.title and self.category:
            self.title = str(self.category)

        # Set upload_date when a document file is first attached
        if self.document and not self.upload_date:
            self.upload_date = timezone.now()

        super().save(*args, **kwargs)
        if self.is_digital_asset:
            if apps.is_installed("asset"):
                from asset.models import Asset, AssetCategory

                asset_category = AssetCategory.objects.get_or_create(
                    asset_category_name="Digital Asset"
                )
                Asset.objects.create(
                    asset_name=self.title or str(self.category or "Document"),
                    asset_purchase_date=date.today(),
                    asset_category_id=asset_category[0],
                    asset_status="Not-Available",
                    asset_purchase_cost=0,
                    expiry_date=self.expiry_date,
                    notify_before=self.notify_before,
                    asset_tracking_id=f"DIG_ID0{self.pk}",
                )

    def upload_documents_count(self):
        total_requests = Document.objects.filter(
            document_request_id=self.document_request_id
        )
        without_documents = total_requests.filter(document="").count()
        count = total_requests.count() - without_documents
        return count
