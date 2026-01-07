from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth.models import AnonymousUser
from core.models import CustomerAuthToken,GrowtagAuthToken,ShopAuthToken


class CustomerTokenAuthentication(BaseAuthentication):
    """
    Header:
      Authorization: Token <key>
    """

    keyword = "Token"

    def authenticate(self, request):
        auth = request.headers.get("Authorization")
        if not auth:
            return None

        parts = auth.split()

        if len(parts) != 2 or parts[0] != self.keyword:
            return None

        token_key = parts[1].strip()
        if not token_key:
            return None

        try:
            token = CustomerAuthToken.objects.select_related("customer").get(key=token_key)
        except CustomerAuthToken.DoesNotExist:
            raise AuthenticationFailed("Invalid token")
       
        #customer = token.customer
        
        request.customer = token.customer
        

        return (token.customer, token)
    
class GrowtagTokenAuthentication(BaseAuthentication):
    keyword = "Token"

    def authenticate(self, request):
        auth = request.headers.get("Authorization")
        if not auth:
            return None

        parts = auth.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            return None

        token_key = parts[1].strip()
        if not token_key:
            return None

        try:
            token = GrowtagAuthToken.objects.select_related("growtag").get(key=token_key)
        except GrowtagAuthToken.DoesNotExist:
            raise AuthenticationFailed("Invalid token")

        request.growtag = token.growtag
        return (token.growtag, token)
    
class ShopTokenAuthentication(BaseAuthentication):
    keyword = "Token"

    def authenticate(self, request):
        auth = request.headers.get("Authorization")
        if not auth:
            return None

        parts = auth.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            return None

        token_key = parts[1].strip()
        if not token_key:
            return None

        try:
            token = ShopAuthToken.objects.select_related("shop").get(key=token_key)
        except ShopAuthToken.DoesNotExist:
            raise AuthenticationFailed("Invalid token")

        request.shop = token.shop
        return (token.shop, token)
