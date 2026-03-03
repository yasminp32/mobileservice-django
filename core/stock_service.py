from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from core.models import InventoryStock, StockLedger  # adjust import as per your structure
from zoho_integration.models import LocalItem


def _get_owner_kwargs(owner_type: str, shop=None, growtag=None):
    
    """
    Role-based owner:
    - exactly one of shop or growtag must be provided
    """
    if bool(shop) == bool(growtag):
        raise ValidationError("Provide exactly one owner: shop OR growtag (not both / not none).")
    return {
        
        "shop": shop if shop else None,
        "growtag": growtag if growtag else None,
    }

def get_stock_balance(*, owner_type: str, item, shop=None, growtag=None):
    owner_kwargs = _get_owner_kwargs(owner_type, shop=shop, growtag=growtag)
    stock = InventoryStock.objects.filter(item=item, **owner_kwargs).first()
    return stock.qty_on_hand if stock and stock.qty_on_hand is not None else Decimal("0.00")


@transaction.atomic
def add_stock(*, item, qty, ref_type="PURCHASE_BILL", ref_id=None, shop=None, growtag=None, note=""):
    qty = Decimal(str(qty))
    if qty <= 0:
        raise ValidationError("add_stock qty must be > 0")

    owner_kwargs = _get_owner_kwargs( shop=shop, growtag=growtag)

    stock, _ = InventoryStock.objects.select_for_update().get_or_create(
        item=item,
        **owner_kwargs,
        defaults={"qty_on_hand": Decimal("0.00")}
    )
    stock.qty_on_hand = (stock.qty_on_hand or Decimal("0.00")) + qty
    stock.full_clean()
    stock.save(update_fields=["qty_on_hand", "updated_at"])

    StockLedger.objects.create(
        item=item,
        qty_change=qty,
        balance_after=stock.qty_on_hand,
        ref_type=ref_type,
        ref_id=ref_id,
        note=note,
        **owner_kwargs,
    )
    return stock


@transaction.atomic
def deduct_stock(*, item, qty, ref_type="INVOICE", ref_id=None, shop=None, growtag=None, note=""):
    qty = Decimal(str(qty))
    if qty <= 0:
        raise ValidationError("deduct_stock qty must be > 0")

    owner_kwargs = _get_owner_kwargs(shop=shop, growtag=growtag)

    stock, _ = InventoryStock.objects.select_for_update().get_or_create(
        item=item,
        **owner_kwargs,
        defaults={"qty_on_hand": Decimal("0.00")}
    )

    available = stock.qty_on_hand or Decimal("0.00")
    if available < qty:
        raise ValidationError(f"Insufficient stock for item={item.id}. Available={available}, required={qty}")

    stock.qty_on_hand = available - qty
    stock.full_clean()
    stock.save(update_fields=["qty_on_hand", "updated_at"])

    StockLedger.objects.create(
        item=item,
        qty_change=-qty,
        balance_after=stock.qty_on_hand,
        ref_type=ref_type,
        ref_id=ref_id,
        note=note,
        **owner_kwargs,
    )
    return stock

@transaction.atomic
def apply_stock_delta(*,item, qty_change, ref_type, ref_id=None, shop=None, growtag=None, note=""):
    qty_change = Decimal(str(qty_change))
    if qty_change == 0:
        return None

    owner_kwargs = _get_owner_kwargs(shop=shop, growtag=growtag)

    stock, _ = InventoryStock.objects.select_for_update().get_or_create(
        item=item,
        **owner_kwargs,
        defaults={"qty_on_hand": Decimal("0.00")}
    )

    new_bal = (stock.qty_on_hand or Decimal("0.00")) + qty_change
    if new_bal < 0:
        raise ValidationError(f"Insufficient stock to apply delta. item={item.id}, delta={qty_change}, bal={stock.qty_on_hand}")

    stock.qty_on_hand = new_bal
    stock.full_clean()
    stock.save(update_fields=["qty_on_hand", "updated_at"])

    StockLedger.objects.create(
        item=item,
        qty_change=qty_change,
        balance_after=stock.qty_on_hand,
        ref_type=ref_type,
        ref_id=ref_id,
        note=note,
        **owner_kwargs
    )
    return stock


@transaction.atomic
def reverse_stock_for_ref(shop, growtag, ref_type, ref_id):
    """
    Rollback all ledger entries for this reference by applying the opposite delta.
    Safe only if ledger rows represent the true history for that ref.
    """

    owner_kwargs = _get_owner_kwargs( shop=shop, growtag=growtag)

    qs = (
        StockLedger.objects
        .select_for_update()
        .filter(ref_type=ref_type, ref_id=ref_id, **owner_kwargs)
        .order_by("id")
    )

    for row in qs:
        # Reverse exactly what happened
        apply_stock_delta(
            
            shop=shop,
            growtag=growtag,
            item=row.item,
            qty_change=-(row.qty_change),   # ✅ reverse the delta
            ref_type="REVERSAL",
            ref_id=ref_id,
            note=f"Reversal of {ref_type} {ref_id}",
        )

    # delete the old rows after reversal
    qs.delete()

from rest_framework.exceptions import ValidationError as DRFValidationError
# keep django ValidationError also if you need it elsewhere

def validate_stock_before_create(*, shop, growtag, payload_lines):
    # aggregate required qty per item
    need = {}
    for ln in payload_lines:
        item_id = ln["item_id"]
        qty = Decimal(str(ln.get("qty", "0")))
        need[item_id] = need.get(item_id, Decimal("0")) + qty

    for item_id, required in need.items():
        item = LocalItem.objects.get(id=item_id)

        available = get_stock_balance(
            
            shop=shop,
            growtag=growtag,
            item=item
        )

        if available < required:
            raise DRFValidationError({
                "detail": f"Insufficient stock for item={item_id}. Available={available}, required={required}"
            })
