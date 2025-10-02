from django.http import HttpResponse


def hx_redirect(url: str) -> HttpResponse:
    """Redirect that works with HTMX."""
    resp = HttpResponse("", status=204)
    resp["HX-Redirect"] = url
    return resp
