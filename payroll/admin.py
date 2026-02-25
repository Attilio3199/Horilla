"""
admin.py

Used to register models on admin site
"""

from django.contrib import admin

from payroll.models.models import (
    Allowance,
    Contract,
    Deduction,
    FilingStatus,
    LoanAccount,
    MultipleCondition,
    Payslip,
    PayslipAutoGenerate,
    Reimbursement,
    ReimbursementrequestComment,
)
from payroll.models.tax_models import PayrollSettings, TaxBracket
from payroll.models.buste_paga_models import (
    BustaPaga,
    CausaleGiorno,
    Causale,
    SezioneAC,
    VoceBusta,
)

# Register your models here.
admin.site.register(FilingStatus)
admin.site.register(TaxBracket)
admin.site.register(Contract)
admin.site.register(Allowance)
admin.site.register(Deduction)
admin.site.register(Payslip)
admin.site.register(PayrollSettings)
admin.site.register(LoanAccount)
admin.site.register(Reimbursement)
admin.site.register(ReimbursementrequestComment)
admin.site.register(MultipleCondition)
admin.site.register(PayslipAutoGenerate)

# Buste paga personalizzate
admin.site.register(BustaPaga)
admin.site.register(SezioneAC)
admin.site.register(Causale)
admin.site.register(CausaleGiorno)
admin.site.register(VoceBusta)
