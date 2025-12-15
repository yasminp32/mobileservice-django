# zoho_integration/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser,JSONParser
from rest_framework import generics
from .models import LocalItem
from .serializers import LocalItemSerializer
from .serializers import LocalItemSerializer
from .zoho_books import (
    build_zoho_item_payload_from_local,
    create_zoho_item,
    update_zoho_item,
    ZohoBooksError,
)
from django.http import JsonResponse
from django.conf import settings
from django.shortcuts import get_object_or_404
from .zoho_books import upload_item_image_to_zoho
from .zoho_books import delete_zoho_item, ZohoBooksError
import requests

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
    return JsonResponse(token_data)
class LocalItemListCreateView(generics.ListCreateAPIView):
    queryset = LocalItem.objects.all().order_by("-id")
    serializer_class = LocalItemSerializer
    parser_classes = [MultiPartParser, FormParser,JSONParser]  # supports JSON + image upload

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)


        # 1) Save locally first
        item = serializer.save(sync_status="PENDING", last_error="")
       

        # 2) Sync to Zoho
        try:
            payload = build_zoho_item_payload_from_local(item)
            
            print("ZOHO PAYLOAD >>>", payload)
            zoho_res = create_zoho_item(payload)

            item.zoho_item_id = (zoho_res.get("item") or {}).get("item_id")
            # 3) Upload image to that Zoho item_id (only if file exists and item_id exists)
            if "item_image" in request.FILES:
              upload_item_image_to_zoho(
                  zoho_item_id=item.zoho_item_id,
                file_obj=request.FILES["item_image"]
                 )
            item.sync_status = "SYNCED"
            item.last_error = ""
            item.save(update_fields=["zoho_item_id", "sync_status", "last_error"])

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
            item.last_error = str(e)
            item.save(update_fields=["sync_status", "last_error"])

            return Response(
                {
                    "detail": "Saved locally but Zoho sync failed",
                    "local_item": LocalItemSerializer(item).data,
                    "error": str(e),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

class LocalItemDetailSyncView(APIView):
    parser_classes = [MultiPartParser, FormParser,JSONParser]

    def get_object(self, pk):
        return LocalItem.objects.get(pk=pk)

    def _save_and_sync(self, request, pk, partial: bool):
        try:
            item = self.get_object(pk)
        except LocalItem.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = LocalItemSerializer(item, data=request.data, partial=partial)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        item = serializer.save(sync_status="PENDING", last_error="")
        
        try:
            payload = build_zoho_item_payload_from_local(item)
            print("ZOHO PAYLOAD >>>", payload)
            # If already synced before → update in Zoho
            if item.zoho_item_id:
                zoho_res = update_zoho_item(item.zoho_item_id, payload)
            else:
                zoho_res = create_zoho_item(payload)
                new_id = (zoho_res.get("item") or {}).get("item_id")
                if new_id:
                    item.zoho_item_id = new_id
                    item.save(update_fields=["zoho_item_id"])

        # 2) If image is sent → upload it to the Zoho item
            if "item_image" in request.FILES:
             upload_item_image_to_zoho(
              zoho_item_id=item.zoho_item_id,
             file_obj=request.FILES["item_image"]
              )


            item.sync_status = "SYNCED"
            item.last_error = ""
            item.save(update_fields=["zoho_item_id", "sync_status", "last_error"])

            return Response(
                {
                    "detail": "Updated locally and synced to Zoho",
                    "local_item": LocalItemSerializer(item).data,
                    "zoho_response": zoho_res,
                },
                status=status.HTTP_200_OK,
            )

        except ZohoBooksError as e:
            item.sync_status = "FAILED"
            item.last_error = str(e)
            item.save(update_fields=["sync_status", "last_error"])
            return Response(
                {"detail": "Updated locally but Zoho sync failed", "error": str(e)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    def put(self, request, pk):
        # Full update (all required fields should be sent)
        return self._save_and_sync(request, pk, partial=False)

    def patch(self, request, pk):
        # Partial update (send only changed fields)
        return self._save_and_sync(request, pk, partial=True)
    def get(self, request, pk):
        item = get_object_or_404(LocalItem, pk=pk)
        return Response(LocalItemSerializer(item).data)
    def delete(self, request, pk):
        try:
           item = self.get_object(pk)
        except LocalItem.DoesNotExist:
           return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    # 1) Delete from Zoho (if synced)
        if item.zoho_item_id:
            try:
               delete_zoho_item(item.zoho_item_id)
            except ZohoBooksError as e:
                return Response(
                   {"detail": "Zoho delete failed. Local not deleted.", "error": str(e)},
                   status=status.HTTP_502_BAD_GATEWAY,
                )

    # 2) Delete local DB record
        item.delete()
        return Response({"detail": "Deleted from Zoho and local DB"}, status=status.HTTP_200_OK)
