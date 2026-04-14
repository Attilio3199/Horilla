from django.contrib import admin

from horilla_documents.models import Document, DocumentRequest, Maternita

# Register your models here.
admin.site.register(Document)
admin.site.register(DocumentRequest)
admin.site.register(Maternita)
