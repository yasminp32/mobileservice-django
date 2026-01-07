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
import requests
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
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
        serializer.save(
            created_by=self.request.user if self.request.user.is_authenticated else None,
            created_on=timezone.now().date()
        )

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

class LocalItemListCreateView(CreatedAuditMixin, generics.ListCreateAPIView):
    queryset = LocalItem.objects.all().order_by("-id")
    serializer_class = LocalItemSerializer
    parser_classes = [MultiPartParser, FormParser,JSONParser]  # supports JSON + image upload

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)


        # 1) Save locally first
        #item = serializer.save(sync_status="PENDING")
        item = serializer.save(
                           sync_status="PENDING",
                           created_by=request.user if request.user.is_authenticated else None,
                           created_on=timezone.now().date(),
                        )
       

        # 2) Sync to Zoho
        try:
            payload = build_zoho_item_payload_from_local(item)
            
            print("ZOHO PAYLOAD >>>", payload)
            zoho_res = create_zoho_item(payload)

            item.zoho_item_id = (zoho_res.get("item") or {}).get("item_id")
            
            item.sync_status = "SYNCED"
            
            item.save(update_fields=["zoho_item_id", "sync_status"])
            # 3) Upload image to that Zoho item_id (only if file exists and item_id exists)
            if "item_image" in request.FILES:
              upload_item_image_to_zoho(
                  zoho_item_id=item.zoho_item_id,
                file_obj=request.FILES["item_image"]
                 )

            return Response(
                {
                    "detail": "Saved locally and synced to Zoho",
                    "local_item": LocalItemSerializer(item).data,
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
                    "local_item": LocalItemSerializer(item).data,
                    "error": str(e),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )



class LocalItemDetailSyncView(generics.RetrieveUpdateDestroyAPIView):
    queryset = LocalItem.objects.all()
    serializer_class = LocalItemSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    def partial_update(self, request, *args, **kwargs):
        """
        ✅ Ensure PATCH works as partial update.
        """
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """
        Handles BOTH PUT and PATCH automatically.
        PUT -> full update
        PATCH -> partial update
        """
        partial = kwargs.pop("partial", False)
        item = self.get_object()

        serializer = self.get_serializer(item, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        # 1) Save locally first
        item = serializer.save(sync_status="PENDING")

        # 2) Sync to Zoho
        try:
            payload = build_zoho_item_payload_from_local(item)
            print("ZOHO PAYLOAD >>>", payload)

            # If already synced → update
            if item.zoho_item_id:
                zoho_res = update_zoho_item(item.zoho_item_id, payload)
            else:
                zoho_res = create_zoho_item(payload)
                new_id = (zoho_res.get("item") or {}).get("item_id")
                if new_id:
                    item.zoho_item_id = new_id
                    item.save(update_fields=["zoho_item_id"])

            # 3) Upload image if sent
            if "item_image" in request.FILES and item.zoho_item_id:
                upload_item_image_to_zoho(
                    zoho_item_id=item.zoho_item_id,
                    file_obj=request.FILES["item_image"],
                )

            item.sync_status = "SYNCED"
            item.save(update_fields=["zoho_item_id", "sync_status"])

            return Response(
                {
                    "detail": "Updated locally and synced to Zoho",
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
        item = self.get_object()

        # 1) Delete from Zoho (if synced)
        if item.zoho_item_id:
            try:
                delete_zoho_item(item.zoho_item_id)
            except ZohoBooksError as e:
                return Response(
                    {"detail": "Zoho delete failed. Local not deleted.", "error": str(e)},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        # 2) Delete local
        item.delete()
        return Response(
            {"detail": "Deleted from Zoho and local DB"},
            status=status.HTTP_200_OK,
        )

    
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


class LocalInvoiceViewSet(CreatedAuditMixin,viewsets.ModelViewSet):
    queryset = LocalInvoice.objects.all().order_by("-id")
    parser_classes = [JSONParser]

    def get_serializer_class(self):
        if self.action in {"list", "retrieve"}:
            return LocalInvoiceReadSerializer
        return LocalInvoiceWriteSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload_lines = serializer.validated_data.pop("lines_payload", [])

        with transaction.atomic():
            #invoice = LocalInvoice.objects.create(**serializer.validated_data)
            invoice = LocalInvoice.objects.create(
                                                 **serializer.validated_data,
                                                 created_by=request.user if request.user.is_authenticated else None,
                                                 created_on=timezone.now().date(),
                                             )

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

        return Response(LocalInvoiceReadSerializer(invoice).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """
        Full update (PUT) – supports replacing lines if lines_payload is provided.
        """
        invoice = self.get_object()
        serializer = self.get_serializer(invoice, data=request.data)
        serializer.is_valid(raise_exception=True)
        payload_lines = serializer.validated_data.pop("lines_payload", None)

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

        return Response(LocalInvoiceReadSerializer(invoice).data, status=status.HTTP_200_OK)

    def partial_update(self, request, *args, **kwargs):
        """
        PATCH – same behavior as update, but partial fields.
        """
        invoice = self.get_object()
        serializer = self.get_serializer(invoice, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        payload_lines = serializer.validated_data.pop("lines_payload", None)

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

        return Response(LocalInvoiceReadSerializer(invoice).data, status=status.HTTP_200_OK)
    
    #invoice pdf
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.template.loader import render_to_string
from decimal import Decimal
from num2words import num2words

def amount_to_words(amount: Decimal) -> str:
    amount = Decimal(amount).quantize(Decimal("0.01"))
    rupees = int(amount)
    paise = int((amount - rupees) * 100)

    rupee_words = num2words(rupees, lang="en_IN").title()

    if paise > 0:
        paise_words = num2words(paise, lang="en_IN").title()
        return f"Indian Rupee {rupee_words} And {paise_words} Paise Only"

    return f"Indian Rupee {rupee_words} Only"


def invoice_pdf_view(request, pk):
    invoice = get_object_or_404(LocalInvoice, pk=pk)

    lines = invoice.lines.select_related("item").all()
    # no saving here

    gst_rows = build_gst_view(invoice)

    # ✅ compute total_tax from saved gst_breakdown (same as your template "Tax" row)
    total_tax = Decimal("0.00")
    for _, v in (invoice.gst_breakdown or {}).items():
        try:
            total_tax += Decimal(v.get("tax", "0.00"))
        except Exception:
            pass

    # ✅ optional: total in words (simple)
    #total_in_words = f"Indian Rupee {invoice.grand_total} Only"
    total_in_words = amount_to_words(invoice.grand_total)

    # ✅ pass EVERYTHING your template expects
    context = {
        "invoice": invoice,
        "lines": lines,
        "total_tax": total_tax,
        "total_in_words": total_in_words,
        "currency_symbol": "₹",
          "gst_rows": gst_rows,
        # company header (optional)
        "company_name": "Nabeel org",
        "company_state": "Kerala",
        "company_country": "India",
        "company_email": "nabeekm18@gmail.com",

        # optional fields used in template
        "terms": "Custom",
        "terms_conditions": invoice.terms_conditions,
        "notes": "Thanks for your business.",
    }

    html_string = render_to_string(
        "invoices/invoice_pdf.html",
        context,
        request=request
    )

    try:
        from weasyprint import HTML
        pdf = HTML(
            string=html_string,
            base_url=request.build_absolute_uri("/")
        ).write_pdf()

        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="invoice_{invoice.id}.pdf"'
        return response

    except Exception:
        # ✅ fallback: show HTML for debugging
        return HttpResponse(html_string)