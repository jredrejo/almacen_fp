from django import forms
from .models import Producto, Ubicacion


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = [
            "nombre",
            "epc",
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


class UbicacionShelfForm(forms.ModelForm):
    class Meta:
        model = Ubicacion
        fields = ["producto", "aula", "estanteria", "posicion"]
