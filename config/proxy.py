import ipaddress

from django.conf import settings


class TrustedProxyHeadersMiddleware:
    """Accept forwarded HTTPS only from explicitly configured proxy networks."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.networks = tuple(
            ipaddress.ip_network(value, strict=False)
            for value in settings.TRUSTED_PROXY_IPS
        )

    def __call__(self, request):
        remote_addr = request.META.get("REMOTE_ADDR", "")
        try:
            trusted = any(ipaddress.ip_address(remote_addr) in network for network in self.networks)
        except ValueError:
            trusted = False
        if not trusted:
            request.META.pop("HTTP_X_FORWARDED_PROTO", None)
        return self.get_response(request)
