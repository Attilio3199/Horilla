from django import template

register = template.Library()


@register.filter(name="paid_amount")
def paid_amount(installment):
    paid = [
        deduction.amount for deduction in installment if deduction.installment_payslip()
    ]

    return sum(paid)


@register.filter(name="balance_amount")
def balance_amount(amount, installment):
    balance = amount - paid_amount(installment)
    return balance


@register.filter(name="italianfloat")
def italianfloat(value):
    """Format a number with 2 decimal places and comma as decimal separator"""
    try:
        num = float(value)
        return "{:.2f}".format(num).replace(".", ",")
    except (ValueError, TypeError):
        return "0,00"
