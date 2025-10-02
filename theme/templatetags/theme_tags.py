from django import template

register = template.Library()


@register.simple_tag
def tailwind_css():
    # In dev, django-tailwind injects; in prod, we fall back to compiled file
    return """<link rel="stylesheet" href="/static/css/tailwind.css">"""
