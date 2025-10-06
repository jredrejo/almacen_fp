from django import forms
from .models import Producto, Ubicacion


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = [
            "epc",
            "nombre",
            "posicion",
            "n_serie",
            "foto",
            "aula",
            "estanteria",
            "cantidad",
            "descripcion",
            "fds",
        ]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
        }


class UbicacionInlineForm(forms.ModelForm):
    """Used in HTMX inline updates within inventory."""

    class Meta:
        model = Ubicacion
        fields = ["estado", "aula", "estanteria", "posicion", "persona"]
