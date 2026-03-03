# core/authentication.py
from rest_framework.authentication import BaseAuthentication
from core.models import CustomerAuthToken, GrowtagAuthToken, ShopAuthToken
from rest_framework import exceptions
def _get_token_key(request):
        auth = request.headers.get("Authorization", "")
        if not auth:
           return None

        # Accept "Token <key>"
        if auth.startswith("Token "):
           return auth.split(" ", 1)[1].strip()

        return None
class UnifiedTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        token_key = _get_token_key(request)
        if not token_key:
            return None

        shop_token = ShopAuthToken.objects.select_related("shop").filter(key=token_key).first()
        if shop_token:
            request.shop = shop_token.shop
            return (None, shop_token)

        growtag_token = GrowtagAuthToken.objects.select_related("growtag").filter(key=token_key).first()
        if growtag_token:
            request.growtag = growtag_token.growtag
            return (None, growtag_token)

        customer_token = CustomerAuthToken.objects.select_related("customer").filter(key=token_key).first()
        if customer_token:
            request.customer = customer_token.customer
            return (None, customer_token)

        raise exceptions.AuthenticationFailed("Invalid token")


class ShopTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        key = _get_token_key(request)
        if not key:
            return None

        try:
            token = ShopAuthToken.objects.select_related("shop").get(key=key)
        except ShopAuthToken.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid shop token")

        request.shop = token.shop
        return (None, token)


class GrowtagTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        key = _get_token_key(request)
        if not key:
            return None

        try:
            token = GrowtagAuthToken.objects.select_related("growtag").get(key=key)
        except GrowtagAuthToken.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid growtag token")

        request.growtag = token.growtag
        return (None, token)


class CustomerTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        key = _get_token_key(request)
        if not key:
            return None

        try:
            token = CustomerAuthToken.objects.select_related("customer").get(key=key)
        except CustomerAuthToken.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid customer token")

        request.customer = token.customer
        return (None, token)