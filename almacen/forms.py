from django import forms
from .models import Producto, Ubicacion, Aula


class ProductoForm(forms.ModelForm):
    def __init__(self, *args, fixed_aula=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fixed_aula = fixed_aula
        if self.fixed_aula is not None:
            # Hide/skip Aula field completely when an aula is fixed
            self.fields.pop("aula", None)

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
            "epc": forms.TextInput(attrs={"class": "form-control"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "posicion": forms.TextInput(attrs={"class": "form-control"}),
            "n_serie": forms.TextInput(attrs={"class": "form-control"}),
            "foto": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "aula": forms.Select(attrs={"class": "form-select"}),
            "estanteria": forms.TextInput(attrs={"class": "form-control"}),
            "cantidad": forms.NumberInput(
                attrs={"class": "form-control", "step": "any"}
            ),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "fds": forms.URLInput(attrs={"class": "form-control"}),
        }


class UbicacionInlineForm(forms.ModelForm):
    """Used in HTMX inline updates within inventory."""

    class Meta:
        model = Ubicacion
        fields = ["estado", "aula", "estanteria", "posicion", "persona"]


class AulaForm(forms.ModelForm):
    class Meta:
        model = Aula
        fields = ["nombre"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
        }
