# zoho_integration/views.py
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework.parsers import MultiPartParser, FormParser,JSONParser
from rest_framework import generics
from .models import LocalItem,LocalInvoice, LocalInvoiceLine
from .serializers import LocalItemSerializer,LocalInvoiceReadSerializer , LocalInvoiceWriteSerializer
from .zoho_books import (
    build_zoho_item_payload_from_local,
    create_zoho_item,
    update_zoho_item,
    ZohoBooksError,
    upload_item_image_to_zoho,
    delete_zoho_item,
    create_zoho_invoice, update_zoho_invoice, build_zoho_invoice_payload_from_local
    
)
from django.http import JsonResponse
from django.conf import settings
from core.mixins import BulkDeleteMixin
from rest_framework.permissions import IsAdminUser
import requests
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.core.exceptions import ValidationError
from core.stock_service import deduct_stock  # import your service
from core.models import StockLedger  # where your StockLedger exists
from core.stock_service import validate_stock_before_create
from core.authentication import (
   UnifiedTokenAuthentication
)
from core.permissions import CrudByRole
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from core.audit import get_actor

def q2(x):
    return (x or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def build_gst_view(invoice):
    rows = []
    breakdown = invoice.gst_breakdown or {}

    for code, v in breakdown.items():
        if code == "NO_TAX":
            continue

        rate = Decimal(str(v.get("rate", "0") or "0"))
        tax = q2(Decimal(str(v.get("tax", "0") or "0")))
        taxable = q2(Decimal(str(v.get("taxable", v.get("amount", invoice.taxable_amount or "0")) or "0")))

        if code.startswith("IGST_"):
            rows.append({
                "mode": "IGST",
                "rate": f"{rate}",
                "tax_total": f"{tax}",
                "taxable": f"{taxable}",
                "igst_rate": f"{rate}",
                "igst_tax": f"{tax}",
                "cgst_rate": None,
                "sgst_rate": None,
                "cgst_tax": None,
                "sgst_tax": None,
            })
        else:
            half_rate = q2(rate / Decimal("2"))
            half_tax = q2(tax / Decimal("2"))

            rows.append({
                "mode": "CGST_SGST",
                "rate": f"{rate}",
                "tax_total": f"{tax}",
                "taxable": f"{taxable}",
                "cgst_rate": f"{half_rate}",
                "sgst_rate": f"{half_rate}",
                "cgst_tax": f"{half_tax}",
                "sgst_tax": f"{half_tax}",
                "igst_rate": None,
                "igst_tax": None,
            })

    return rows

def _norm_state(s: str) -> str:
    return (s or "").strip().lower()


def _is_inter_state(invoice, company_state="Kerala") -> bool:
    customer_state = _norm_state(getattr(invoice.customer, "state", ""))
    comp_state = _norm_state(company_state)

    # ✅ If customer state missing → SAME state (GST)
    if not customer_state:
        return False

    return customer_state != comp_state
def _to_igst(code: str) -> str:
    if not code or code == "NO_TAX": return "NO_TAX"
    if code.startswith("IGST_"): return code
    if code.startswith("GST_"): return "IGST_" + code.split("_", 1)[1]
    return code

def _to_gst(code: str) -> str:
    if not code or code == "NO_TAX": return "NO_TAX"
    if code.startswith("GST_"): return code
    if code.startswith("IGST_"): return "GST_" + code.split("_", 1)[1]
    return code

    

# Common audit helpers
class CreatedAuditMixin:
    def perform_create(self, serializer):
        role, actor = get_actor(self.request)

        data = {"created_on": timezone.now().date()}

        if role == "admin":
            data["created_by"] = actor
            data["created_by_role"] = "admin"
        elif role == "shop":
            data["created_by_role"] = "shop"
            data["created_by_shop"] = actor
        elif role == "growtag":
            data["created_by_role"] = "growtag"
            data["created_by_growtag"] = actor
        elif role == "customer":
            data["created_by_role"] = "customer"
            data["created_by_customer"] = actor

        serializer.save(**data)
def zoho_callback(request):
    code = request.GET.get("code")

    if not code:
        return JsonResponse({"error": "Missing code"}, status=400)

    token_url = "https://accounts.zoho.in/oauth/v2/token"

    data = {
        "grant_type": "authorization_code",
        "client_id": settings.ZOHO_CLIENT_ID,
        "client_secret": settings.ZOHO_CLIENT_SECRET,
        "redirect_uri": settings.ZOHO_REDIRECT_URI,
        "code": code,
    }

    r = requests.post(token_url, data=data)
    token_data = r.json()

    # 🔥 THIS IS WHERE YOU SEE TOKENS
    #return JsonResponse(token_data)
    print("ZOHO TOKEN RESPONSE >>>", token_data)
    return JsonResponse({"detail": "Token received. Check server logs."})

LOCAL_ONLY_FIELDS = {"opening_stock", "current_stock", "is_active", "item_image"}


class LocalItemListCreateView(BulkDeleteMixin, CreatedAuditMixin, generics.ListCreateAPIView):
    serializer_class = LocalItemSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    authentication_classes = [JWTAuthentication, SessionAuthentication, UnifiedTokenAuthentication]
    permission_classes = [IsAdminUser]
    def get_queryset(self):
        # ✅ show only active items by default
        return LocalItem.objects.filter(is_active=True).order_by("-id")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # ✅ Save locally first
        item = serializer.save(
            sync_status="PENDING",
            created_by=request.user if request.user.is_authenticated else None,
            created_on=timezone.now().date(),
        )

        # ✅ If you want to skip Zoho sync for some cases, keep this always True for create
        should_sync_zoho = True

        if not should_sync_zoho:
            item.sync_status = "SYNCED"
            item.save(update_fields=["sync_status"])
            return Response(
                {"detail": "Saved locally (Zoho sync skipped)", "local_item": self.get_serializer(item).data},
                status=status.HTTP_201_CREATED,
            )

        # ✅ Sync to Zoho
        try:
            payload = build_zoho_item_payload_from_local(item)
            zoho_res = create_zoho_item(payload)

            item.zoho_item_id = (zoho_res.get("item") or {}).get("item_id")
            item.sync_status = "SYNCED"
            item.save(update_fields=["zoho_item_id", "sync_status"])

            # ✅ Upload image if sent
            if "item_image" in request.FILES and item.zoho_item_id:
                upload_item_image_to_zoho(
                    zoho_item_id=item.zoho_item_id,
                    file_obj=request.FILES["item_image"],
                )

            return Response(
                {
                    "detail": "Saved locally and synced to Zoho",
                    "local_item": self.get_serializer(item).data,
                    "zoho_response": zoho_res,
                },
                status=status.HTTP_201_CREATED,
            )

        except ZohoBooksError as e:
            item.sync_status = "FAILED"
            item.save(update_fields=["sync_status"])

            return Response(
                {
                    "detail": "Saved locally but Zoho sync failed",
                    "local_item": self.get_serializer(item).data,
                    "error": str(e),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
class LocalItemDetailSyncView(BulkDeleteMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = LocalItem.objects.all()
    serializer_class = LocalItemSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    permission_classes = [IsAdminUser]
    authentication_classes = [JWTAuthentication, SessionAuthentication, UnifiedTokenAuthentication]

    def get_object(self):
        # You can keep default or block retrieving inactive items if you want:
        # return get_object_or_404(LocalItem, pk=self.kwargs["pk"], is_active=True)
        return super().get_object()

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        item = self.get_object()

        serializer = self.get_serializer(item, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        # ✅ Save locally first
        item = serializer.save(sync_status="PENDING")

        # ✅ Decide if Zoho sync is really needed
        request_fields = set(request.data.keys())

        # local-only changes: no need Zoho update
        # If request includes any non-local-only field => sync Zoho
        should_sync_zoho = len(request_fields - LOCAL_ONLY_FIELDS) > 0

        # If only image uploaded, we still may need zoho upload (but not update payload)
        image_sent = "item_image" in request.FILES

        try:
            zoho_res = None

            if should_sync_zoho:
                payload = build_zoho_item_payload_from_local(item)

                # If already synced → update
                if item.zoho_item_id:
                    zoho_res = update_zoho_item(item.zoho_item_id, payload)
                else:
                    zoho_res = create_zoho_item(payload)
                    new_id = (zoho_res.get("item") or {}).get("item_id")
                    if new_id:
                        item.zoho_item_id = new_id
                        item.save(update_fields=["zoho_item_id"])

            # ✅ Upload image if sent and Zoho ID exists
            if image_sent and item.zoho_item_id:
                upload_item_image_to_zoho(
                    zoho_item_id=item.zoho_item_id,
                    file_obj=request.FILES["item_image"],
                )

            item.sync_status = "SYNCED"
            item.save(update_fields=["sync_status", "zoho_item_id"])

            return Response(
                {
                    "detail": "Updated locally" + (" and synced to Zoho" if should_sync_zoho else " (Zoho sync skipped)"),
                    "local_item": self.get_serializer(item).data,
                    "zoho_response": zoho_res,
                },
                status=status.HTTP_200_OK,
            )

        except ZohoBooksError as e:
            item.sync_status = "FAILED"
            item.save(update_fields=["sync_status"])

            return Response(
                {
                    "detail": "Updated locally but Zoho sync failed",
                    "local_item": self.get_serializer(item).data,
                    "error": str(e),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

    def destroy(self, request, *args, **kwargs):
        """
        ✅ Soft delete locally (is_active=False)
        ✅ Optionally delete from Zoho
        """
        item = self.get_object()

        # Optional: delete from Zoho
        if item.zoho_item_id:
            try:
                delete_zoho_item(item.zoho_item_id)
            except ZohoBooksError as e:
                return Response(
                    {"detail": "Zoho delete failed. Local not deactivated.", "error": str(e)},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        # ✅ Soft delete
        item.is_active = False
        item.save(update_fields=["is_active"])

        return Response({"detail": "Item deactivated (soft deleted)"}, status=status.HTTP_200_OK)


    
    #invoice
# ===============================
# HELPERS (TOP OF FILE)
# ===============================

def _q2(x: Decimal) -> Decimal:
    return (x or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def recompute_invoice_totals(invoice: LocalInvoice) -> None:
    """
    Recompute invoice totals based on stored line fields.
    NOTE: This implementation treats discount as AFTER tax (simple + consistent).
    If you want discount BEFORE tax, tell me and I’ll give the proportional-tax version.
    """
    lines = invoice.lines.all()

    sub_total = _q2(sum((l.line_amount for l in lines), Decimal("0")))
    service_total = _q2(sum((l.service_charge_amount for l in lines), Decimal("0")))
    taxable_amount = _q2(sum((l.taxable_amount for l in lines), Decimal("0")))
    grand_before_discount = _q2(sum((l.line_total for l in lines), Decimal("0")))

    # discount
    discount_amount = Decimal("0")
    if invoice.discount_type == "PERCENT":
        pct = Decimal(invoice.discount_value or 0)
        if pct < 0:
            pct = Decimal("0")
        if pct > 100:
            pct = Decimal("100")
        discount_amount = _q2((grand_before_discount * pct) / Decimal("100"))
    else:
        discount_amount = _q2(Decimal(invoice.discount_value or 0))

    if discount_amount > grand_before_discount:
        discount_amount = grand_before_discount

    grand_total = _q2(grand_before_discount - discount_amount)
    inter = _is_inter_state(invoice, company_state="Kerala")
    # GST breakup aggregate by gst_treatment
    gst_breakdown = {}
    for l in lines:
        key = l.gst_treatment or "NO_TAX"
        key = _to_igst(key) if inter else _to_gst(key) 
        if key not in gst_breakdown:
            gst_breakdown[key] = {"rate": str(l._gst_rate_percent()), "tax": "0.00", "taxable": "0.00"}
        gst_breakdown[key]["tax"] = str(_q2(Decimal(gst_breakdown[key]["tax"]) + Decimal(l.line_tax)))
        gst_breakdown[key]["taxable"] = str(_q2(Decimal(gst_breakdown[key]["taxable"]) + Decimal(l.taxable_amount)))

    invoice.sub_total = sub_total
    invoice.service_charge_total = service_total
    invoice.taxable_amount = taxable_amount
    invoice.discount_amount = discount_amount
    invoice.gst_breakdown = gst_breakdown
    invoice.grand_total = grand_total

FINAL_STATUSES = {"PAID", "PARTIALLY_PAID"}


def get_invoice_owner(invoice: LocalInvoice):
    """
    Decide invoice owner using existing fields:
    assigned_shop OR assigned_growtag
    """
    if invoice.assigned_shop_id and invoice.assigned_growtag_id:
        raise ValidationError("Invoice cannot have both assigned_shop and assigned_growtag.")

    if invoice.assigned_shop_id:
        return ("shop", invoice.assigned_shop, None)

    if invoice.assigned_growtag_id:
        return ("growtag", None, invoice.assigned_growtag)

    raise ValidationError("Invoice must have assigned_shop OR assigned_growtag.")


def has_invoice_stock_deducted(invoice: LocalInvoice) -> bool:
    owner_type, shop, growtag = get_invoice_owner(invoice)
    return StockLedger.objects.filter(
        owner_type=owner_type,
        shop=shop if owner_type == "shop" else None,
        growtag=growtag if owner_type == "growtag" else None,
        ref_type="INVOICE",
        ref_id=invoice.id,
    ).exists()

class LocalInvoiceViewSet(BulkDeleteMixin,CreatedAuditMixin,viewsets.ModelViewSet):
    queryset = LocalInvoice.objects.all().order_by("-id")
    authentication_classes = [
        JWTAuthentication,SessionAuthentication,
        UnifiedTokenAuthentication,
    ]
    permission_classes = [CrudByRole]

    role_perms = {
        "admin": {"GET", "POST", "PATCH", "DELETE","PUT"},
        "franchise": {"GET", "POST", "PATCH","PUT"},
        "othershop": {"GET", "POST", "PATCH","PUT"},
        "growtag": {"GET","POST","PATCH","PUT"},
        "customer": {"GET"},   # optional
    }
    def get_serializer_class(self):
        if self.action in {"list", "retrieve"}:
            return LocalInvoiceReadSerializer
        return LocalInvoiceWriteSerializer
    def get_queryset(self):
       qs = super().get_queryset()

       # ✅ Admin sees all
       if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
          return qs

        # ✅ Shop sees only its invoices
       if getattr(self.request, "shop", None):
          return qs.filter(assigned_shop=self.request.shop)

        # ✅ Growtag sees only its invoices
       if getattr(self.request, "growtag", None):
          return qs.filter(assigned_growtag=self.request.growtag)

       # ✅ Customer sees only own invoices (optional)
       if getattr(self.request, "customer", None):
          return qs.filter(customer_id=self.request.customer.id)

       return qs.none()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload_lines = serializer.validated_data.pop("lines_payload", [])

        # get owner from request data (because invoice not created yet)
        # ✅ ADMIN: can use payload owner
        if request.user and request.user.is_authenticated and request.user.is_staff:
           assigned_shop = serializer.validated_data.get("assigned_shop")
           assigned_growtag = serializer.validated_data.get("assigned_growtag")

        # ✅ SHOP: force assigned_shop from token
        elif getattr(request, "shop", None):
            serializer.validated_data["assigned_shop"] = request.shop
            serializer.validated_data["assigned_growtag"] = None
            assigned_shop = request.shop
            assigned_growtag = None

        # ✅ GROWTAG: force assigned_growtag from token (or block create)
        elif getattr(request, "growtag", None):
            serializer.validated_data["assigned_growtag"] = request.growtag
            serializer.validated_data["assigned_shop"] = None
            assigned_shop = None
            assigned_growtag = request.growtag

# ✅ CUSTOMER: block create
        elif getattr(request, "customer", None):
          raise PermissionDenied("Customer cannot create invoice.")

        else:
           raise PermissionDenied("Not allowed.")


        if assigned_shop and assigned_growtag:
          raise ValidationError("Invoice cannot be assigned to both shop and growtag.")
        if not assigned_shop and not assigned_growtag:
          raise ValidationError("Invoice must be assigned to either shop or growtag.")

        owner_type = "shop" if assigned_shop else "growtag"
        shop = assigned_shop if owner_type == "shop" else None
        growtag = assigned_growtag if owner_type == "growtag" else None

        # ✅ Validate stock BEFORE invoice create
        if serializer.validated_data.get("status") in FINAL_STATUSES:
           validate_stock_before_create(
                                       owner_type=owner_type,
                                       shop=shop,
                                       growtag=growtag,
                                       payload_lines=payload_lines
                                       )


        with transaction.atomic():
            #invoice = LocalInvoice.objects.create(**serializer.validated_data)
            #invoice = LocalInvoice.objects.create(
                                                 #**serializer.validated_data,
                                                 #created_by=request.user if request.user.is_authenticated else None,
                                                 #created_on=timezone.now().date(),
                                             #)
             # ✅ role-based created_by / created_by_role
            role, actor = get_actor(request)

            create_kwargs = dict(serializer.validated_data)
            create_kwargs["created_on"] = timezone.now().date()

            if role == "admin":
              create_kwargs["created_by"] = actor
              create_kwargs["created_by_role"] = "admin"

            elif role in ("franchise", "othershop", "shop"):
              # your system treats shop tokens as franchise/othershop
              create_kwargs["created_by_role"] = role
              create_kwargs["created_by_shop"] = actor

            elif role == "growtag":
               create_kwargs["created_by_role"] = "growtag"
               create_kwargs["created_by_growtag"] = actor

            elif role == "customer":
               create_kwargs["created_by_role"] = "customer"
               create_kwargs["created_by_customer"] = actor

            invoice = LocalInvoice.objects.create(**create_kwargs)

            # create lines
            bad_items = []
            for i, line in enumerate(payload_lines):
                local_item_id = line["item_id"]
                try:
                    item = LocalItem.objects.get(id=local_item_id)
                except LocalItem.DoesNotExist:
                    bad_items.append(local_item_id)
                    continue

                LocalInvoiceLine.objects.create(
                    invoice=invoice,
                    item=item,
                    qty=line["qty"],
                    rate=line["rate"],
                    description=line.get("description", ""),
                    service_charge_type=line.get("service_charge_type", "AMOUNT"),
                    service_charge_value=line.get("service_charge_value", Decimal("0")),
                    gst_treatment=line.get("gst_treatment", invoice.apply_gst_to_all_items or "NO_TAX"),
                    #created_by=request.user if request.user.is_authenticated else None,
                    #created_on=timezone.now().date(),
                )

            if bad_items:
                raise ValueError(f"Invalid item_id(s): {bad_items}")

            # totals
            recompute_invoice_totals(invoice)
            invoice.save(update_fields=[
                "sub_total", "service_charge_total", "taxable_amount",
                "discount_amount", "gst_breakdown", "grand_total"
            ])
                        # ✅ stock deduction (only if PAID/PARTIALLY_PAID)
            self._apply_stock_deduction_if_final(invoice)
        # ✅ If no lines, skip Zoho sync (Zoho requires at least 1 item)
        if not invoice.lines.exists():
          invoice.sync_status = "PENDING"   # or "NOT_READY"
          invoice.last_error = ""
          invoice.save(update_fields=["sync_status", "last_error", "updated_at"])
          return Response(LocalInvoiceReadSerializer(invoice).data, status=status.HTTP_201_CREATED)

        # Sync to Zoho (outside atomic ok, but we update invoice after)
        try:
            zoho_payload = build_zoho_invoice_payload_from_local(invoice)
            zoho_res = create_zoho_invoice(zoho_payload)

            inv_obj = zoho_res.get("invoice") or {}
            invoice.zoho_invoice_id = str(inv_obj.get("invoice_id") or "")
            invoice.sync_status = "SYNCED"
            invoice.last_error = ""
            invoice.save(update_fields=["zoho_invoice_id", "sync_status", "last_error"])
        except ZohoBooksError as e:
            invoice.sync_status = "FAILED"
            invoice.last_error = str(e)
            invoice.save(update_fields=["sync_status", "last_error"])
        

        except Exception as e:
            invoice.sync_status = "FAILED"
            invoice.last_error = str(e)
            invoice.save(update_fields=["sync_status", "last_error"])
        if request.query_params.get("pdf") == "1":
           return invoice_pdf_view(request, pk=invoice.pk)
        #return Response(LocalInvoiceReadSerializer(invoice).data, status=status.HTTP_201_CREATED)
        return Response(
               LocalInvoiceReadSerializer(invoice, context={"request": request}).data,
              status=status.HTTP_200_OK
            )

    def update(self, request, *args, **kwargs):
        """
        Full update (PUT) – supports replacing lines if lines_payload is provided.
        """
        invoice = self.get_object()
         

        # ✅ Shop: cannot edit invoices after FINAL or stock deducted

        if getattr(request, "shop", None):
          if invoice.assigned_shop_id != request.shop.id:
             raise PermissionDenied("You cannot edit this invoice.")
          if invoice.status in FINAL_STATUSES or has_invoice_stock_deducted(invoice):
             raise PermissionDenied("Cannot edit after invoice is finalized / stock deducted.")

        # ✅ Growtag: usually block, or allow limited fields
        if getattr(request, "growtag", None):
            if invoice.assigned_growtag_id != request.growtag.id:
              raise PermissionDenied("You cannot edit this invoice.")
            if invoice.status in FINAL_STATUSES or has_invoice_stock_deducted(invoice):
              raise PermissionDenied("Cannot edit after invoice is finalized / stock deducted.")
        old_status = invoice.status
        serializer = self.get_serializer(invoice, data=request.data)
        serializer.is_valid(raise_exception=True)
        payload_lines = serializer.validated_data.pop("lines_payload", None)
        if payload_lines is not None and has_invoice_stock_deducted(invoice):
           raise ValidationError("Cannot edit invoice lines after stock is deducted.")
        with transaction.atomic():
            for k, v in serializer.validated_data.items():
                setattr(invoice, k, v)
            invoice.save()

            # replace lines only if provided
            if payload_lines is not None:
                invoice.lines.all().delete()

                bad_items = []
                for line in payload_lines:
                    local_item_id = line["item_id"]
                    try:
                        item = LocalItem.objects.get(id=local_item_id)
                    except LocalItem.DoesNotExist:
                        bad_items.append(local_item_id)
                        continue

                    LocalInvoiceLine.objects.create(
                        invoice=invoice,
                        item=item,
                        qty=line["qty"],
                        rate=line["rate"],
                        description=line.get("description", ""),
                        service_charge_type=line.get("service_charge_type", "AMOUNT"),
                        service_charge_value=line.get("service_charge_value", Decimal("0")),
                        gst_treatment=line.get("gst_treatment", invoice.apply_gst_to_all_items or "NO_TAX"),
                    )

                if bad_items:
                    raise ValueError(f"Invalid item_id(s): {bad_items}")

            recompute_invoice_totals(invoice)
            invoice.save(update_fields=[
                "sub_total", "service_charge_total", "taxable_amount",
                "discount_amount", "gst_breakdown", "grand_total"
            ])
            if old_status not in FINAL_STATUSES and invoice.status in FINAL_STATUSES:
                self._apply_stock_deduction_if_final(invoice)
        if not invoice.lines.exists():
          invoice.sync_status = "PENDING"
          invoice.last_error = ""
          invoice.save(update_fields=["sync_status", "last_error", "updated_at"])
          return Response(LocalInvoiceReadSerializer(invoice).data, status=status.HTTP_200_OK)

        # Zoho sync: if zoho_invoice_id exists => update, else create
        try:
            zoho_payload = build_zoho_invoice_payload_from_local(invoice)
            if invoice.zoho_invoice_id:
                zoho_res = update_zoho_invoice(invoice.zoho_invoice_id, zoho_payload)
            else:
                zoho_res = create_zoho_invoice(zoho_payload)
                inv_obj = zoho_res.get("invoice") or {}
                invoice.zoho_invoice_id = str(inv_obj.get("invoice_id") or "")

            invoice.sync_status = "SYNCED"
            invoice.last_error = ""
            invoice.save(update_fields=["zoho_invoice_id", "sync_status", "last_error"])
        except ZohoBooksError as e:
            invoice.sync_status = "FAILED"
            invoice.last_error = str(e)
            invoice.save(update_fields=["sync_status", "last_error"])    

        except Exception as e:
            invoice.sync_status = "FAILED"
            invoice.last_error = str(e)
            invoice.save(update_fields=["sync_status", "last_error"])
        if request.query_params.get("pdf") == "1":
           return invoice_pdf_view(request, pk=invoice.pk)
        #return Response(LocalInvoiceReadSerializer(invoice).data, status=status.HTTP_200_OK)
        return Response(
             LocalInvoiceReadSerializer(invoice, context={"request": request}).data,
                 status=status.HTTP_200_OK
            )

    def partial_update(self, request, *args, **kwargs):
        """
        PATCH – same behavior as update, but partial fields.
        """
        invoice = self.get_object()
        # ✅ Shop: cannot edit invoices after FINAL or stock deducted
        if getattr(request, "shop", None):
          if invoice.assigned_shop_id != request.shop.id:
            raise PermissionDenied("You cannot edit this invoice.")
          if invoice.status in FINAL_STATUSES or has_invoice_stock_deducted(invoice):
            raise PermissionDenied("Cannot edit after invoice is finalized / stock deducted.")

        # ✅ Growtag: usually block, or allow limited fields
        if getattr(request, "growtag", None):
          if invoice.assigned_growtag_id != request.growtag.id:
            raise PermissionDenied("You cannot edit this invoice.")
        # safest:
          raise PermissionDenied("Growtag cannot edit invoice.")

        old_status = invoice.status

        serializer = self.get_serializer(invoice, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        payload_lines = serializer.validated_data.pop("lines_payload", None)

        if payload_lines is not None and has_invoice_stock_deducted(invoice):
          raise ValidationError("Cannot edit invoice lines after stock is deducted.")
        with transaction.atomic():
            for k, v in serializer.validated_data.items():
                setattr(invoice, k, v)
            invoice.save()

            if payload_lines is not None:
                invoice.lines.all().delete()

                bad_items = []
                for line in payload_lines:
                    local_item_id = line["item_id"]
                    try:
                        item = LocalItem.objects.get(id=local_item_id)
                    except LocalItem.DoesNotExist:
                        bad_items.append(local_item_id)
                        continue

                    LocalInvoiceLine.objects.create(
                        invoice=invoice,
                        item=item,
                        qty=line["qty"],
                        rate=line["rate"],
                        description=line.get("description", ""),
                        service_charge_type=line.get("service_charge_type", "AMOUNT"),
                        service_charge_value=line.get("service_charge_value", Decimal("0")),
                        gst_treatment=line.get("gst_treatment", invoice.apply_gst_to_all_items or "NO_TAX"),
                    )

                if bad_items:
                    raise ValueError(f"Invalid item_id(s): {bad_items}")

            recompute_invoice_totals(invoice)
            invoice.save(update_fields=[
                "sub_total", "service_charge_total", "taxable_amount",
                "discount_amount", "gst_breakdown", "grand_total"
            ])
            if old_status not in FINAL_STATUSES and invoice.status in FINAL_STATUSES:
              try:
                self._apply_stock_deduction_if_final(invoice)
              except ValidationError as e:
                   return Response({"detail": e.messages}, status=status.HTTP_400_BAD_REQUEST)

        if not invoice.lines.exists():
            invoice.sync_status = "PENDING"
            invoice.last_error = ""
            invoice.save(update_fields=["sync_status", "last_error", "updated_at"])
            return Response(LocalInvoiceReadSerializer(invoice).data, status=status.HTTP_200_OK)

        # optional: sync patch too (same logic)
        try:
            zoho_payload = build_zoho_invoice_payload_from_local(invoice)
            if invoice.zoho_invoice_id:
                update_zoho_invoice(invoice.zoho_invoice_id, zoho_payload)
            else:
                zoho_res = create_zoho_invoice(zoho_payload)
                inv_obj = zoho_res.get("invoice") or {}
                invoice.zoho_invoice_id = str(inv_obj.get("invoice_id") or "")
        
            invoice.sync_status = "SYNCED"
            invoice.last_error = ""
            invoice.save(update_fields=["zoho_invoice_id", "sync_status", "last_error"])
        except ZohoBooksError as e:
            invoice.sync_status = "FAILED"
            invoice.last_error = str(e)
            invoice.save(update_fields=["sync_status", "last_error"])
    

        except Exception as e:
            invoice.sync_status = "FAILED"
            invoice.last_error = str(e)
            invoice.save(update_fields=["sync_status", "last_error"])
        if request.query_params.get("pdf") == "1":
           return invoice_pdf_view(request, pk=invoice.pk)
        #return Response(LocalInvoiceReadSerializer(invoice).data, status=status.HTTP_200_OK)
        return Response(
             LocalInvoiceReadSerializer(invoice, context={"request": request}).data,
             status=status.HTTP_200_OK
            )
    
    def _apply_stock_deduction_if_final(self, invoice: LocalInvoice):
        """
        Deduct stock only for PAID/PARTIALLY_PAID and only once.
        """
        if invoice.status not in FINAL_STATUSES:
            return

        if has_invoice_stock_deducted(invoice):
            return  # ✅ already deducted

        owner_type, shop, growtag = get_invoice_owner(invoice)

        for ln in invoice.lines.select_related("item").all():
            deduct_stock(
                owner_type=owner_type,
                shop=shop,
                growtag=growtag,
                item=ln.item,
                qty=ln.qty,
                ref_type="INVOICE",
                ref_id=invoice.id,
                note=f"Stock deducted from Invoice {invoice.invoice_number}",
            )
    
    #invoice pdf
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.template.loader import render_to_string
from decimal import Decimal
from num2words import num2words
from rest_framework.decorators import api_view, authentication_classes, permission_classes

def amount_to_words(amount: Decimal) -> str:
    amount = Decimal(amount).quantize(Decimal("0.01"))
    rupees = int(amount)
    paise = int((amount - rupees) * 100)

    rupee_words = num2words(rupees, lang="en_IN").title()

    if paise > 0:
        paise_words = num2words(paise, lang="en_IN").title()
        return f"Indian Rupee {rupee_words} And {paise_words} Paise Only"

    return f"Indian Rupee {rupee_words} Only"


#invoice pdf view
from decimal import Decimal
import os

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_RIGHT  
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image
from reportlab.lib.enums import TA_CENTER
import os
from pathlib import Path

def _register_unicode_font():
    font_path = os.path.join(settings.BASE_DIR, "fonts", "NotoSans-Regular.ttf")
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont("NotoSans", font_path))
        return "NotoSans"
    return "Helvetica"


def money(val):
    try:
        return f"₹ {Decimal(val):.2f}"
    except Exception:
        return f"₹ {val}"


@api_view(["GET"])
@authentication_classes([JWTAuthentication, SessionAuthentication, UnifiedTokenAuthentication])
@permission_classes([CrudByRole])
def invoice_pdf_view(request, pk):
    invoice = get_object_or_404(LocalInvoice, pk=pk)

    # ✅ permissions
    u = getattr(request, "user", None)
    if u and u.is_authenticated and u.is_staff:
        pass
    elif getattr(request, "shop", None):
        if invoice.assigned_shop_id != request.shop.id:
            raise PermissionDenied
    elif getattr(request, "growtag", None):
        if invoice.assigned_growtag_id != request.growtag.id:
            raise PermissionDenied
    elif getattr(request, "customer", None):
        if invoice.customer_id != request.customer.id:
            raise PermissionDenied
    else:
        raise PermissionDenied

    lines = invoice.lines.select_related("item").all()
    gst_rows = build_gst_view(invoice)

    total_tax = Decimal("0.00")
    for _, v in (invoice.gst_breakdown or {}).items():
        try:
            total_tax += Decimal(v.get("tax", "0.00"))
        except Exception:
            pass

    total_in_words = amount_to_words(invoice.grand_total)

    base_font = _register_unicode_font()
    print("Using font:", base_font)

    # ✅ IMPORTANT: styles defined here (this fixes your NameError)
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="InvTitle",
        parent=styles["Title"],
        fontName=base_font,
        fontSize=24,
        leading=28,
        spaceAfter=8,
        textColor=colors.HexColor("#0f172a"),
    ))

    styles.add(ParagraphStyle(
        name="InvSmall",
        parent=styles["Normal"],
        fontName=base_font,
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#475569"),
    ))

    styles.add(ParagraphStyle(
        name="InvBody",
        parent=styles["Normal"],
        fontName=base_font,
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#0f172a"),
    ))

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="invoice_{invoice.id}.pdf"'

    doc = SimpleDocTemplate(
        response,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Invoice {invoice.invoice_number}",
    )

    elements = []

    # Header
    logo_path = Path(settings.BASE_DIR) / "static" / "img" / "logo.jpg"  # adjust path
    
    if os.path.exists(logo_path):
        logo = Image(logo_path)
        logo.drawHeight = 25 * mm   # adjust size
        logo.drawWidth = 60 * mm    # adjust size
        logo.hAlign = "LEFT"      # center logo

        elements.append(logo)
        elements.append(Spacer(1, 8))  # space below logo
    elements.append(Paragraph("INVOICE", styles["InvTitle"]))

    right_style = ParagraphStyle(
        "OrgRight",
        parent=styles["InvSmall"],
        alignment=TA_RIGHT
        )

    left_block = Paragraph(
        f'Invoice Number: <b>{invoice.invoice_number}</b><br/>'
        f'Date: <b>{invoice.invoice_date}</b>',
        styles["InvSmall"]
        )

    right_block = Paragraph(
        "<b>Nabeel org</b><br/>Kerala, India<br/>nabeekm18@gmail.com",
        right_style
        )

    #header_tbl = Table([[left_block, right_block]], colWidths=[110*mm, 60*mm])
    header_tbl = Table([[left_block, right_block]], colWidths=[112*mm, 60*mm], hAlign="LEFT")  # 172mm
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
         ]))
    elements.append(header_tbl)
    elements.append(Spacer(1, 10))

    # Items table
    data = [["#", "Item", "Qty", "Rate", "Service", "GST", "Amount"]]
    for i, ln in enumerate(lines, start=1):
        gst_text = "0%"
        if getattr(ln, "gst_treatment", None) and ln.gst_treatment != "NO_TAX":
            gst_text = f"{ln.gst_treatment}%"
        data.append([
            str(i),
            (ln.item.name if ln.item else ""),
            str(ln.qty),
            money(ln.rate),
            money(ln.service_charge_amount),
            gst_text,
            money(ln.line_total),
        ])

    tbl = Table(
    data,
    colWidths=[10*mm, 58*mm, 12*mm, 22*mm, 24*mm, 20*mm, 26*mm],  # ✅ GST wider
    repeatRows=1,hAlign="LEFT"
    )

    tbl.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), base_font),  # ✅ applies to whole table (fixes ₹)
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1e4d86")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTSIZE", (0,0), (-1,0), 10),
        ("FONTSIZE", (0,1), (-1,-1), 10),

        ("GRID", (0,0), (-1,-1), 0.8, colors.HexColor("#cfd8e3")),

        ("ALIGN", (2,1), (2,-1), "RIGHT"),   # Qty
        ("ALIGN", (3,1), (4,-1), "RIGHT"),   # Rate + Service
        ("ALIGN", (6,1), (6,-1), "RIGHT"),   # Amount
        ("ALIGN", (5,1), (5,-1), "CENTER"),  # ✅ GST center
        ("ALIGN", (5,0), (5,0), "CENTER"),   # GST header center

        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    elements.append(tbl)
    elements.append(Spacer(1, 10))

    # Totals
    totals = [
        ["Sub Total", money(invoice.sub_total)],
        ["Discount (-)", money(invoice.discount_amount)],
        ["Service Charge", money(invoice.service_charge_total)],
        ["Total Tax", money(total_tax)],
        ["TOTAL", money(invoice.grand_total)],
        ["Balance Due", money(invoice.grand_total)],
    ]
    #t = Table(totals, colWidths=[60*mm, 35*mm])
    t = Table(totals, colWidths=[35*mm, 25*mm],hAlign="LEFT")  # total 60mm
    t.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.8, colors.HexColor("#cfd8e3")),
        ("FONTNAME", (0,0), (-1,-1), base_font),
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
        ("BACKGROUND", (0,4), (-1,4), colors.HexColor("#1e4d86")),
        ("TEXTCOLOR", (0,4), (-1,4), colors.white),
        ("BACKGROUND", (0,5), (-1,5), colors.HexColor("#f1f5f9")),
    ]))
        # Left side: Terms + Total in Words
    terms_content = invoice.terms_conditions or "-"

    left_section = [
        Paragraph("<b>Total In Words</b>", styles["InvBody"]),
        Spacer(1, 4),
        Paragraph(f"<i>{total_in_words}</i>", styles["InvBody"]),
        Spacer(1, 10),
        Paragraph("<b>Terms and Conditions</b>", styles["InvBody"]),
        Spacer(1, 4),
        Paragraph(terms_content, styles["InvSmall"]),
    ]

    # Wrap left section inside a box
    #left_box = Table([[left_section]], colWidths=[95*mm])
    left_box = Table([[left_section]], colWidths=[112*mm])
    left_box.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 0.8, colors.HexColor("#cfd8e3")),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
        
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
    ]))

    # Right side: Totals table (already created as variable t)
    bottom_section = Table([[left_box, t]], colWidths=[112*mm,60*mm ], hAlign="LEFT")
    #bottom_section = Table([[left_box, t]], colWidths=[95*mm, 60*mm])
    bottom_section.setStyle(TableStyle([
       ("VALIGN", (0,0), (-1,-1), "TOP"),
       ("LEFTPADDING", (0,0), (-1,-1), -1),
    ]))

    elements.append(bottom_section)
    elements.append(Spacer(1, 10))

    doc.build(elements)
    return response


# role perms
invoice_pdf_view.cls.role_perms = {
    "admin": {"GET"},
    "franchise": {"GET"},
    "othershop": {"GET"},
    "growtag": {"GET"},
    "customer": set(),
}