# core/utils.py

from decimal import Decimal, ROUND_HALF_UP

def generate_po_number():
    import uuid
    return f"PO-{uuid.uuid4().hex[:8].upper()}"

def q2(x: Decimal) -> Decimal:
    return (x or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def recompute_purchase_order_totals(purchase_order):
    subtotal = Decimal("0.00")
    total_discount = Decimal("0.00")
    total_tax = Decimal("0.00")

    for item in purchase_order.items.all():
        qty = Decimal(item.qty or 0)
        unit_price = Decimal(item.unit_price or 0)
        discount_percent = Decimal(item.discount_percent or 0)
        tax_percent = Decimal(item.tax_percent or 0)

        line_subtotal = q2(qty * unit_price)
        discount_amount = q2((line_subtotal * discount_percent) / Decimal("100"))
        taxable_amount = q2(line_subtotal - discount_amount)
        tax_amount = q2((taxable_amount * tax_percent) / Decimal("100"))
        line_total = q2(taxable_amount + tax_amount)

        item.line_subtotal = line_subtotal
        item.discount_amount = discount_amount
        item.tax_amount = tax_amount
        item.line_total = line_total
        item.save(update_fields=["line_subtotal", "discount_amount", "tax_amount", "line_total"])

        subtotal += line_subtotal
        total_discount += discount_amount
        total_tax += tax_amount

    subtotal = q2(subtotal)
    total_discount = q2(total_discount)
    total_tax = q2(total_tax)

    shipping = Decimal(purchase_order.shipping_charges or 0)
    adjustment = Decimal(purchase_order.adjustment or 0)

    grand_total = q2(subtotal - total_discount + total_tax + q2(shipping) + q2(adjustment))

    purchase_order.subtotal = subtotal
    purchase_order.total_discount = total_discount
    purchase_order.total_tax = total_tax
    purchase_order.grand_total = grand_total

    purchase_order.save(update_fields=["subtotal", "total_discount", "total_tax", "grand_total"])

