
from decimal import Decimal

from django.utils import timezone
from django.db.models import Count, Sum,DecimalField, Value
from django.db.models.functions import TruncMonth,Coalesce

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from core.authentication import UnifiedTokenAuthentication
from core.models import Complaint, Shop, Growtags
from core.permissions import IsAdminOrGrowtagSelf,IsAdminOrShopSelf
from zoho_integration.models import LocalInvoice
import calendar
from django.db.models import Min
from django.db.models.functions import ExtractYear
from rest_framework_simplejwt.authentication import JWTAuthentication

class AdminDashboardAPIView(APIView):
    permission_classes = [IsAdminUser]

    PAID_INVOICE_STATUSES = ["PAID", "PARTIALLY_PAID"]
    ADMIN_SHARE = Decimal("0.20")

    def get(self, request):
        today = timezone.localdate()
        year = int(request.query_params.get("year", today.year))

        # ✅ Jan-Dec labels fixed
        labels = [calendar.month_abbr[i] for i in range(1, 13)]

        # -------------------------
        # TOP CARDS
        # -------------------------
        total_complaints = Complaint.objects.filter(created_at__year=year).count()
        total_growtags = Growtags.objects.filter(created_at__year=year).count()
        franchise_shops = Shop.objects.filter(shop_type="franchise", created_at__year=year).count()
        other_shops = Shop.objects.filter(shop_type="othershop", created_at__year=year).count()

        # ✅ Total Service Charge (100%) for selected year
        total_service_charge = LocalInvoice.objects.filter(
           status__in=self.PAID_INVOICE_STATUSES,
           invoice_date__year=year
        ).aggregate(
            s=Coalesce(
               Sum("service_charge_total"),   # ✅ CHANGED
               Value(0),
               output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["s"]

        # ✅ Admin Earnings (20%) from service charge
        admin_earnings = total_service_charge * self.ADMIN_SHARE   # ✅ CHANGED


        # -------------------------
        # SUMMARY CARDS
        # (keep your status names if they are exactly these)
        # -------------------------
        # today only makes sense for current year
        today_complaints = Complaint.objects.filter(created_at__date=today).count() if year == today.year else 0

        pending_complaints = Complaint.objects.filter(created_at__year=year, status="Pending").count()
        active_complaints = Complaint.objects.filter(created_at__year=year, status__in=["Assigned", "In Progress"]).count()
        resolved_complaints = Complaint.objects.filter(created_at__year=year, status="Resolved").count()

        # -------------------------
        # CHART: Complaints Overview (Jan-Dec)
        # -------------------------
        complaints_arr = [0] * 12

        complaints_monthly = (
            Complaint.objects.filter(created_at__year=year)
            .annotate(m=TruncMonth("created_at"))
            .values("m")
            .annotate(cnt=Count("id"))
        )

        for row in complaints_monthly:
            complaints_arr[row["m"].month - 1] = row["cnt"]

        # -------------------------
        # CHART: Admin Revenue Trend (Jan-Dec) = 20% of grand_total
        # -------------------------
        admin_revenue_arr = [0] * 12

        revenue_monthly = (
            LocalInvoice.objects.filter(
                status__in=self.PAID_INVOICE_STATUSES,
                invoice_date__year=year
            )
            .annotate(m=TruncMonth("invoice_date"))
            .values("m")
            .annotate(
                total_amt=Coalesce(
                    Sum("service_charge_total"),
                    Value(0),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
        )

        for r in revenue_monthly:
            idx = r["m"].month - 1
            admin_revenue_arr[idx] = float(r["total_amt"] * self.ADMIN_SHARE)

        # -------------------------
        # CHART: GrowTags Growth (Jan-Dec)
        # -------------------------
        growtags_arr = [0] * 12

        growtags_monthly = (
            Growtags.objects.filter(created_at__year=year)
            .annotate(m=TruncMonth("created_at"))
            .values("m")
            .annotate(cnt=Count("id"))
        )

        for g in growtags_monthly:
            growtags_arr[g["m"].month - 1] = g["cnt"]

        # -------------------------
        # CHART: Franchise & Other shops growth (Jan-Dec)
        # -------------------------
        franchise_arr = [0] * 12
        other_arr = [0] * 12

        franchise_qs = (
            Shop.objects.filter(shop_type="franchise", created_at__year=year)
            .annotate(m=TruncMonth("created_at"))
            .values("m")
            .annotate(cnt=Count("id"))
        )
        for s in franchise_qs:
            franchise_arr[s["m"].month - 1] = s["cnt"]

        other_qs = (
            Shop.objects.filter(shop_type="othershop", created_at__year=year)
            .annotate(m=TruncMonth("created_at"))
            .values("m")
            .annotate(cnt=Count("id"))
        )
        for s in other_qs:
            other_arr[s["m"].month - 1] = s["cnt"]

        # -------------------------
        # Growth performance bar (use admin earnings)
        # -------------------------
        growth_performance = {
            "complaints": total_complaints,
            "growtags": total_growtags,
            "franchise_shops": franchise_shops,
            "other_shops": other_shops,
            "admin_earnings": float(admin_earnings),
        }

        return Response({
            "year": year,
            "cards": {
                "total_complaints": total_complaints,
                "total_growtags": total_growtags,
                "franchise_shops": franchise_shops,
                "other_shops": other_shops,

                # ✅ this is 20% earnings
                "total_earnings": float(admin_earnings),

                # optional: keep this if frontend wants 100% total amount
                #"total_amount": float(total_amount),
            },
            "summary": {
                "today_complaints": today_complaints,
                "pending_complaints": pending_complaints,
                "active_complaints": active_complaints,
                "resolved_complaints": resolved_complaints,
            },
            "charts": {
                "complaints_overview": {
                    "labels": labels,
                    "totals": complaints_arr,
                },
                "revenue_trend": {
                    "labels": labels,
                    "amounts": admin_revenue_arr,  # ✅ 20% trend
                },
                "growtags_growth": {
                    "labels": labels,
                    "totals": growtags_arr,
                },
                "franchise_shops_growth": {
                    "labels": labels,
                    "totals": franchise_arr,
                },
                "other_shops_growth": {
                    "labels": labels,
                    "totals": other_arr,
                },
                "growth_performance": growth_performance,
            }
        })

class GrowtagDashboardAPIView(APIView):
    
    authentication_classes = [UnifiedTokenAuthentication,JWTAuthentication]
    permission_classes = [IsAdminOrGrowtagSelf]
    DONE_COMPLAINT_STATUSES = ["Completed", "Resolved"]
    PAID_INVOICE_STATUSES = ["PAID", "PARTIALLY_PAID"]

    # ✅ Only GrowTag share used
    GROWTAG_SHARE = Decimal("0.40")

    def get(self, request):
        
        today = timezone.localdate()
        try:
          year = int(request.query_params.get("year", today.year))
        except ValueError:
             year = today.year
        # ✅ decide target growtag
        if request.user and request.user.is_staff:
            # admin can pass growtag_id
            growtag_id = request.query_params.get("growtag_id")
            if not growtag_id:
                return Response({"detail": "growtag_id is required"}, status=400)
            growtag = Growtags.objects.filter(id=growtag_id).first()
            if not growtag:
                return Response({"detail": "Invalid growtag_id"}, status=400)
        else:
            # growtag can ONLY see own dashboard
            growtag = request.growtag
            growtag_id = growtag.id


        # ==================================================
        # Complaints (Growtag)
        # ==================================================
        cqs = Complaint.objects.filter(assigned_Growtags_id=growtag_id)
        cqs_year = cqs.filter(created_at__year=year)

        total_assigned = cqs_year.count()
        completed_work = cqs_year.filter(status__in=self.DONE_COMPLAINT_STATUSES).count()
        pending_work = cqs_year.exclude(status__in=self.DONE_COMPLAINT_STATUSES).count()

        # today card only for current year
        todays_complaints = (
                   cqs.filter(created_at__date=today).count()
                   if year == today.year
                   else 0
                )


        # ==================================================
        # Charts: Always Jan → Dec
        # ==================================================
        labels = [calendar.month_abbr[i] for i in range(1, 13)]
        assigned_arr = [0] * 12
        resolved_arr = [0] * 12
        earnings_arr = [0] * 12  # ✅ Growtag 40% trend

        # --------------------------
        # Complaints Overview Chart
        # --------------------------
        assigned_qs = (
             cqs_year
            .annotate(m=TruncMonth("created_at"))
            .values("m")
            .annotate(cnt=Count("id"))
            )

        resolved_qs = (
                cqs_year.filter(status__in=self.DONE_COMPLAINT_STATUSES)
               .annotate(m=TruncMonth("created_at"))
               .values("m")
               .annotate(cnt=Count("id"))
              )


        for row in assigned_qs:
            assigned_arr[row["m"].month - 1] = row["cnt"]

        for row in resolved_qs:
            resolved_arr[row["m"].month - 1] = row["cnt"]

        # ==================================================
        # Invoices (Growtag) + Growtag earnings 40%
        # ==================================================
        inv_qs = LocalInvoice.objects.filter(
            assigned_growtag_id=growtag_id,
            status__in=self.PAID_INVOICE_STATUSES,
        ).exclude(invoice_date__isnull=True)

        # Monthly totals (100%), convert to Growtag 40% for chart
        monthly_total_qs = (
            inv_qs.filter(invoice_date__year=year)
            .annotate(m=TruncMonth("invoice_date"))
            .values("m")
            .annotate(
                total_amt=Coalesce(
                    Sum("service_charge_total"),
                    Value(0),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
        )

        for row in monthly_total_qs:
            idx = row["m"].month - 1
            month_total = row["total_amt"]  # Decimal
            earnings_arr[idx] = float(month_total * self.GROWTAG_SHARE)

        # Year total (100%)
        total_service_charge = inv_qs.filter(invoice_date__year=year).aggregate(
            s=Coalesce(
                Sum("service_charge_total"),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["s"]  # Decimal

        # ✅ Growtag Total Earnings (40%)
        total_earnings = total_service_charge * self.GROWTAG_SHARE

        # ==================================================
        # FINAL RESPONSE
        # ==================================================
        return Response({
            "growtag": {
                "id": growtag.id,
                "name": getattr(growtag, "name", None) or str(growtag)
            },
            "date": str(today),
            "year": year,

            "cards": {
                "total_assigned_complaints": total_assigned,
                "todays_complaints": todays_complaints,
                "completed_work": completed_work,
                "pending_work": pending_work,

                
                # ✅ MAIN: Growtag 40% earnings
                "total_earnings": float(total_earnings),
            },

            "charts": {
                "complaints_overview": {
                    "labels": labels,
                    "assigned": assigned_arr,
                    "resolved": resolved_arr,
                },
                # ✅ Growtag 40% trend Jan-Dec
                "earnings_trend": {
                    "labels": labels,
                    "amounts": earnings_arr,
                },
            },
        })

class OtherShopDashboardAPIView(APIView):
    
    authentication_classes = [UnifiedTokenAuthentication,JWTAuthentication]
    permission_classes = [IsAdminOrShopSelf] 

    DONE_COMPLAINT_STATUSES = ["Completed", "Resolved"]

    PAID_INVOICE_STATUSES = ["PAID", "PARTIALLY_PAID"]

    SHOP_SHARE = Decimal("0.40")  # ✅ Othershop earnings share

    def get(self, request):
        today = timezone.localdate()
        year = int(request.query_params.get("year", today.year))
        if request.user and request.user.is_staff:
            shop_id = request.query_params.get("shop_id")
            if not shop_id:
                return Response({"detail": "shop_id is required"}, status=400)
            shop = Shop.objects.filter(id=shop_id, shop_type="othershop").first()
            if not shop:
                return Response({"detail": "Invalid shop_id or not an othershop"}, status=400)
        else:
            shop = request.shop
            if shop.shop_type != "othershop":
                return Response({"detail": "Only othershop can access this dashboard"}, status=403)
            shop_id = shop.id


        # ==================================================
        # Complaints (OtherShop)
        # ==================================================
        cqs = Complaint.objects.filter(assigned_shop_id=shop_id)
        cqs_year = cqs.filter(created_at__year=year)

        total_assigned = cqs_year.count()
        completed_work = cqs_year.filter(status__in=self.DONE_COMPLAINT_STATUSES).count()
        pending_work = cqs_year.exclude(status__in=self.DONE_COMPLAINT_STATUSES).count()

        # today card only makes sense when year == current year
        todays_complaints = (
            cqs.filter(created_at__date=today).count()
            if year == today.year
            else 0
        )


        # ==================================================
        # Charts: Always Jan → Dec
        # ==================================================
        labels = [calendar.month_abbr[i] for i in range(1, 13)]

        assigned_arr = [0] * 12
        resolved_arr = [0] * 12
        shop_earnings_arr = [0] * 12  # ✅ 40% earnings trend

        # --------------------------
        # Complaints Overview Chart
        # (assigned vs resolved monthly)
        # --------------------------
        assigned_qs = (
            cqs.filter(created_at__year=year)
            .annotate(m=TruncMonth("created_at"))
            .values("m")
            .annotate(cnt=Count("id"))
        )

        resolved_qs = (
              cqs.filter(created_at__year=year, status__in=self.DONE_COMPLAINT_STATUSES)
              .annotate(m=TruncMonth("created_at"))
              .values("m")
               .annotate(cnt=Count("id"))
             )


        for row in assigned_qs:
            assigned_arr[row["m"].month - 1] = row["cnt"]

        for row in resolved_qs:
            resolved_arr[row["m"].month - 1] = row["cnt"]

        # ==================================================
        # Earnings (OtherShop invoices) + 40% share
        # ==================================================
        inv_qs = LocalInvoice.objects.filter(
            assigned_shop_id=shop_id,
            status__in=self.PAID_INVOICE_STATUSES,
        ).exclude(invoice_date__isnull=True)  # ✅ optional safety

        # Monthly total (100%) → convert to shop 40% for chart
        monthly_total_qs = (
            inv_qs.filter(invoice_date__year=year)
            .annotate(m=TruncMonth("invoice_date"))
            .values("m")
            .annotate(
                total_amt=Coalesce(
                    Sum("service_charge_total"),
                    Value(0),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
        )

        for row in monthly_total_qs:
            idx = row["m"].month - 1
            month_total = row["total_amt"]  # Decimal
            shop_earnings_arr[idx] = float(month_total * self.SHOP_SHARE)

        # Year total amount (100%)
        total_service_charge = inv_qs.filter(invoice_date__year=year).aggregate(
            s=Coalesce(
                Sum("service_charge_total"),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["s"]

        # ✅ Shop total earnings (40%)
        shop_earnings =  total_service_charge * self.SHOP_SHARE

        # ==================================================
        # FINAL RESPONSE
        # ==================================================
        return Response({
            "shop": {
                "id": shop.id,
                "name": getattr(shop, "shopname", None) or str(shop),
                "shop_type": shop.shop_type,
            },
            "date": str(today),
            "year": year,

            "cards": {
                "total_assigned_complaints": total_assigned,
                "todays_complaints": todays_complaints,
                "completed_work": completed_work,
                "pending_work": pending_work,

                # Money
                "total_service_charge": float(total_service_charge),          # 100%
                "total_earnings": float(shop_earnings),       # ✅ 40% (main for shop dashboard)
            },

            "charts": {
                "complaints_overview": {
                    "labels": labels,
                    "assigned": assigned_arr,
                    "resolved": resolved_arr,
                },
                "revenue_growth": {   # (like screenshot line chart)
                    "labels": labels,
                    "amounts": shop_earnings_arr,  # ✅ 40% trend Jan-Dec
                },
            },
        })
class FranchiseDashboardAPIView(APIView):
    authentication_classes = [UnifiedTokenAuthentication,JWTAuthentication]
    permission_classes = [IsAdminOrShopSelf] 
    
    DONE_COMPLAINT_STATUSES = ["Completed", "Resolved"]

    PAID_INVOICE_STATUSES = ["PAID", "PARTIALLY_PAID"]

    SHOP_SHARE = Decimal("0.40")  # ✅ franchise earnings share

    def get(self, request):
        
        today = timezone.localdate()
        year = int(request.query_params.get("year", today.year))
        if request.user and request.user.is_staff:
            shop_id = request.query_params.get("shop_id")
            if not shop_id:
                return Response({"detail": "shop_id is required"}, status=400)

            shop = Shop.objects.filter(id=shop_id, shop_type="franchise").first()
            if not shop:
                return Response({"detail": "Invalid shop_id or not a franchise"}, status=400)

        else:
            shop = request.shop
            if shop.shop_type != "franchise":
                return Response({"detail": "Only franchise can access this dashboard"}, status=403)
            shop_id = shop.id
        # ==================================================
        # Complaints (Franchise shop)
        # ==================================================
        cqs = Complaint.objects.filter(assigned_shop_id=shop_id)
        cqs_year = cqs.filter(created_at__year=year)

        total_assigned = cqs_year.count()
        completed_work = cqs_year.filter(status__in=self.DONE_COMPLAINT_STATUSES).count()
        pending_work = cqs_year.exclude(status__in=self.DONE_COMPLAINT_STATUSES).count()

        # today card only makes sense when year == current year
        todays_complaints = (
            cqs.filter(created_at__date=today).count()
            if year == today.year
            else 0
        )


        # ✅ optional card: work assigned to growtag (from this shop complaints)
        work_assigned_to_growtag = cqs.filter(assigned_Growtags__isnull=False).count()

        # ✅ optional card: my growtags count (depends on your relation; safe fallback)
        # If you have a FK like Growtags.assigned_shop or Growtags.shop, adjust below.
        my_growtags_count = 0
        try:
            my_growtags_count = Growtags.objects.filter(shop_id=shop_id).count()
        except Exception:
            my_growtags_count = 0

        # ==================================================
        # Charts Jan → Dec
        # ==================================================
        labels = [calendar.month_abbr[i] for i in range(1, 13)]
        assigned_arr = [0] * 12
        resolved_arr = [0] * 12
        franchise_earnings_arr = [0] * 12  # ✅ 40% trend

        # --------------------------
        # Complaints Overview Chart
        # --------------------------
        assigned_qs = (
            cqs.filter(created_at__year=year)
            .annotate(m=TruncMonth("created_at"))
            .values("m")
            .annotate(cnt=Count("id"))
        )

        resolved_qs = (
             cqs.filter(created_at__year=year, status__in=self.DONE_COMPLAINT_STATUSES)
             .annotate(m=TruncMonth("created_at"))
             .values("m")
             .annotate(cnt=Count("id"))
              )


        for row in assigned_qs:
            assigned_arr[row["m"].month - 1] = row["cnt"]

        for row in resolved_qs:
            resolved_arr[row["m"].month - 1] = row["cnt"]

        # ==================================================
        # Invoices (Franchise shop) + 40% share
        # ==================================================
        inv_qs = LocalInvoice.objects.filter(
            assigned_shop_id=shop_id,
            status__in=self.PAID_INVOICE_STATUSES,
        ).exclude(invoice_date__isnull=True)

        monthly_total_qs = (
            inv_qs.filter(invoice_date__year=year)
            .annotate(m=TruncMonth("invoice_date"))
            .values("m")
            .annotate(
                total_amt=Coalesce(
                    Sum("service_charge_total"),
                    Value(0),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
        )

        for row in monthly_total_qs:
            idx = row["m"].month - 1
            month_total = row["total_amt"]
            franchise_earnings_arr[idx] = float(month_total * self.SHOP_SHARE)

        total_service_charge = inv_qs.filter(invoice_date__year=year).aggregate(
            s=Coalesce(
                Sum("service_charge_total"),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["s"]

        franchise_earnings = total_service_charge * self.SHOP_SHARE

        # ==================================================
        # FINAL RESPONSE
        # ==================================================
        return Response({
            "shop": {
                "id": shop.id,
                "name": getattr(shop, "shopname", None) or str(shop),
                "shop_type": shop.shop_type,
            },
            "date": str(today),
            "year": year,

            "cards": {
                "total_assigned_complaints": total_assigned,
                "todays_complaints": todays_complaints,
                "my_growtags_count": my_growtags_count,                 # optional
                #"total_amount": float(total_amount),                    # 100%
                "total_earnings": float(franchise_earnings),            # ✅ 40% (main)
                "completed_work": completed_work,
                "pending_work": pending_work,
                "work_assigned_to_growtag": work_assigned_to_growtag,   # optional
            },

            "charts": {
                "complaints_overview": {
                    "labels": labels,
                    "assigned": assigned_arr,
                    "resolved": resolved_arr,
                },
                "revenue_growth": {
                    "labels": labels,
                    "amounts": franchise_earnings_arr,  # ✅ 40% trend
                },
            },
        })
    
#year dropdown

class AdminDashboardMetaAPIView(APIView):
    
    permission_classes = [IsAdminUser]

    def get(self, request):
        current_year = timezone.localdate().year

        # Prefer invoice start year (most reliable for revenue dashboards)
        min_invoice_year = (
            LocalInvoice.objects
            .exclude(invoice_date__isnull=True)
            .annotate(y=ExtractYear("invoice_date"))
            .aggregate(min_y=Min("y"))
            .get("min_y")
        )

        # Fallback to complaints if invoices not available
        min_complaint_year = (
            Complaint.objects
            .exclude(created_at__isnull=True)
            .annotate(y=ExtractYear("created_at"))
            .aggregate(min_y=Min("y"))
            .get("min_y")
        )

        start_year = min_invoice_year or min_complaint_year or current_year
        start_year = int(start_year)

        years = list(range(start_year, current_year + 1))

        return Response({
            "start_year": start_year,
            "current_year": current_year,
            "years": years,
            "default_year": current_year,
        })
class GrowtagDashboardMetaAPIView(APIView):
    authentication_classes = [UnifiedTokenAuthentication,JWTAuthentication]
    permission_classes = [IsAdminOrGrowtagSelf]

    def get(self, request):
        growtag_id = request.query_params.get("growtag_id")
        if not growtag_id:
            return Response({"detail": "growtag_id is required"}, status=400)
        if not Growtags.objects.filter(id=growtag_id).exists():
            return Response({"detail": "Invalid growtag_id"}, status=400)

        current_year = timezone.localdate().year

        min_invoice_year = (
            LocalInvoice.objects
            .filter(assigned_growtag_id=growtag_id)
            .exclude(invoice_date__isnull=True)
            .annotate(y=ExtractYear("invoice_date"))
            .aggregate(min_y=Min("y"))
            .get("min_y")
        )

        min_complaint_year = (
            Complaint.objects
            .filter(assigned_Growtags_id=growtag_id)
            .exclude(created_at__isnull=True)
            .annotate(y=ExtractYear("created_at"))
            .aggregate(min_y=Min("y"))
            .get("min_y")
        )

        start_year = min_invoice_year or min_complaint_year or current_year
        start_year = int(start_year)
        if start_year > current_year:
            start_year = current_year

        years = list(range(start_year, current_year + 1))

        return Response({
            "start_year": start_year,
            "current_year": current_year,
            "years": years,
            "default_year": current_year,
        })
class ShopDashboardMetaAPIView(APIView):
    authentication_classes = [UnifiedTokenAuthentication,JWTAuthentication]
    permission_classes = [IsAdminOrShopSelf]

    def get(self, request):
        shop_id = request.query_params.get("shop_id")
        if not shop_id:
            return Response({"detail": "shop_id is required"}, status=400)

        shop = Shop.objects.filter(id=shop_id).first()
        if not shop:
            return Response({"detail": "Invalid shop_id"}, status=400)

        current_year = timezone.localdate().year

        min_invoice_year = (
            LocalInvoice.objects
            .filter(assigned_shop_id=shop_id)
            .exclude(invoice_date__isnull=True)
            .annotate(y=ExtractYear("invoice_date"))
            .aggregate(min_y=Min("y"))
            .get("min_y")
        )

        min_complaint_year = (
            Complaint.objects
            .filter(assigned_shop_id=shop_id)
            .exclude(created_at__isnull=True)
            .annotate(y=ExtractYear("created_at"))
            .aggregate(min_y=Min("y"))
            .get("min_y")
        )

        start_year = min_invoice_year or min_complaint_year or current_year
        start_year = int(start_year)

        if start_year > current_year:
            start_year = current_year

        years = list(range(start_year, current_year + 1))

        return Response({
            "shop": {
                "id": shop.id,
                "name": getattr(shop, "shopname", None) or str(shop),
                "shop_type": shop.shop_type,
            },
            "start_year": start_year,
            "current_year": current_year,
            "years": years,
            "default_year": current_year,
        })
