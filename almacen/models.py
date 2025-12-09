from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class Aula(models.Model):
    OPERATION_MODE_CHOICES = [
        ("WITH_PERSONA", "Con identificación de persona"),
        ("WITHOUT_PERSONA", "Sin identificación de persona"),
    ]

    nombre = models.CharField(max_length=100, unique=True)
    operation_mode = models.CharField(
        "Modo de operación",
        max_length=20,
        choices=OPERATION_MODE_CHOICES,
        default="WITH_PERSONA",
        help_text="Modo de operación para esta aula: WITH_PERSONA requiere identificar persona para préstamos, WITHOUT_PERSONA permite préstamos sin identificación.",
    )

    class Meta:
        verbose_name = "Aula"
        verbose_name_plural = "Aulas"

    def __str__(self):
        return f"{self.nombre} - {self.id}"


class Producto(models.Model):
    # Código EPC RFID (leído por el lector; típicamente emulación de teclado)
    epc = models.CharField("EPC", max_length=96, unique=True)
    nombre = models.CharField(max_length=255)
    posicion = models.CharField(max_length=100, blank=True)
    n_serie = models.CharField("Nº de serie", max_length=255, blank=True)
    foto = models.ImageField(upload_to="productos/", blank=True, null=True)
    aula = models.ForeignKey(Aula, on_delete=models.PROTECT, related_name="productos")
    estanteria = models.CharField(max_length=100, blank=True)
    cantidad = models.FloatField(default=1.0)
    descripcion = models.TextField(blank=True)
    fds = models.URLField("FDS (hoja de datos)", blank=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    @property
    def current_prestamo(self):
        # requiere Prestamo(producto=..., devuelto_en is null) para significar "actualmente tomado"
        return (
            self.prestamos.filter(devuelto_en__isnull=True)  # type: ignore[attr-defined]
            .select_related("usuario")
            .first()
        )

    @property
    def is_taken(self):
        return self.current_prestamo is not None

    @property
    def taken_by(self):
        return self.current_prestamo.usuario if self.current_prestamo else None

    class Meta:
        ordering = ["nombre"]
        verbose_name = "Producto"
        verbose_name_plural = "Productos"

    def __str__(self):
        return f"{self.nombre} ({self.epc})"


class Persona(models.Model):
    """Optional profile table if you want extra fields; we just map to User."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="persona")
    last_aula = models.ForeignKey(
        "Aula",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="preferida_por",
    )
    aulas_access: "models.ManyToManyField" = models.ManyToManyField(  # type: ignore[assignment]
        "Aula",
        blank=True,
        verbose_name="Aulas accesibles",
        help_text="Aulas a las que esta persona tiene acceso. Si está vacío, tiene acceso a todas las aulas.",
    )
    epc = models.CharField(
        "EPC", max_length=96, unique=True, default=None, blank=True, null=True
    )

    def get_aulas_access(self):
        """Return list of accessible Aulas. Staff users see all aulas, others see only assigned aulas."""
        if self.user.is_staff:
            return Aula.objects.all()
        return self.aulas_access.all()

    def has_aula_access(self, aula):
        """Check if user has access to specific aula."""
        if self.user.is_staff:
            return True
        return aula in self.aulas_access.all()

    def __str__(self):
        return self.user.get_full_name() or self.user.email


class Ubicacion(models.Model):
    ESTADO_CHOICES = [
        ("ESTANTE", "En estantería"),
        ("PERSONA", "En manos de una persona"),
    ]
    producto = models.OneToOneField(
        Producto, on_delete=models.CASCADE, related_name="ubicacion"
    )
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default="ESTANTE")
    # Cuando está en estantería:
    aula = models.ForeignKey(
        Aula,
        on_delete=models.PROTECT,
        related_name="ubicaciones",
        null=True,
        blank=True,
    )
    estanteria = models.CharField(max_length=100, blank=True)
    posicion = models.CharField(max_length=100, blank=True)
    # Cuando está tomado:
    persona = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="productos_tomados",
        null=True,
        blank=True,
    )
    tomado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Ubicación"
        verbose_name_plural = "Ubicaciones"

    def __str__(self):
        return f"{self.producto} - {self.estado}"


class Prestamo(models.Model):
    """Historial de acciones de tomar/devolver para consulta rápida y auditoría."""

    producto = models.ForeignKey(
        Producto, on_delete=models.CASCADE, related_name="prestamos"
    )
    usuario = models.ForeignKey(  # type: ignore[call-overload]
        User,
        on_delete=models.PROTECT,
        related_name="prestamos",
        null=True,
        blank=True,
        default=None,
    )
    tomado_en = models.DateTimeField(auto_now_add=True)
    devuelto_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-tomado_en"]
        verbose_name = "Préstamo"
        verbose_name_plural = "Préstamos"

    def __str__(self):
        return f"{self.producto} → {self.usuario}"
