from django.conf import settings
from django.db import models
from django.utils import timezone


class Aula(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    codigo = models.CharField(max_length=50, unique=True)  # e.g., A101

    def __str__(self):
        return f"{self.nombre} ({self.codigo})"


class Producto(models.Model):
    nombre = models.CharField(max_length=255)
    epc = models.CharField("EPC (RFID)", max_length=96, unique=True)
    posicion = models.CharField(max_length=120, blank=True)
    n_serie = models.CharField(max_length=120, blank=True)
    foto = models.ImageField(upload_to="productos/", blank=True, null=True)
    aula = models.ForeignKey(Aula, on_delete=models.PROTECT, related_name="productos")
    estanteria = models.CharField(max_length=120, blank=True)
    cantidad = models.FloatField(default=1)
    descripcion = models.TextField(blank=True)
    fds = models.URLField("Ficha de seguridad (FDS)", blank=True)

    # denormalized convenience fields for current holder
    holder = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="prestamos",
    )
    holder_desde = models.DateTimeField(null=True, blank=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre", "aula_id"]

    def __str__(self):
        return self.nombre

    @property
    def en_prestamo(self):
        return self.holder_id is not None


class Ubicacion(models.Model):
    """Event log of where a product is (shelf vs checked out). Required by spec."""

    class Tipo(models.TextChoices):
        ESTANTERIA = "SHELF", "En estantería"
        PRESTAMO = "CO", "En préstamo"

    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name="ubicaciones")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    aula = models.ForeignKey(Aula, on_delete=models.PROTECT)
    estanteria = models.CharField(max_length=120, blank=True)
    posicion = models.CharField(max_length=120, blank=True)

    persona = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        base = f"{self.producto} → {self.get_tipo_display()}"
        if self.persona:
            base += f" ({self.persona})"
        return base
