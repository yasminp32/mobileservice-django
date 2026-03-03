# core/mixins.py
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser

class BulkDeleteMixin:
    """
    POST /<resource>/bulk-delete/
    body: { "ids": [1,2,3] }
    """
    @action(
        detail=False,
        methods=["post"],
        url_path="bulk-delete",
        permission_classes=[IsAdminUser],  # change if needed
    )
    def bulk_delete(self, request):
        ids = request.data.get("ids", [])

        if not isinstance(ids, list) or not ids:
            return Response(
                {"detail": "ids must be a non-empty list"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_ids = []
        for x in ids:
            try:
                valid_ids.append(int(x))
            except (TypeError, ValueError):
                pass

        if not valid_ids:
            return Response(
                {"detail": "No valid ids provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = self.get_queryset().filter(id__in=valid_ids)
        found = qs.count()

        if found == 0:
            return Response(
                {"detail": "No records found for given ids"},
                status=status.HTTP_404_NOT_FOUND,
            )

        deleted_count, _ = qs.delete()

        return Response(
            {"requested": len(ids), "found": found, "deleted": deleted_count},
            status=status.HTTP_200_OK,
        )
