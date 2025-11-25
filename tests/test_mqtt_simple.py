"""
Test simple para verificar que el la lógica de creación de prestamos con el listener MQTT funciona correctamente.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from almacen.management.commands.mqtt_listener import BatchProcessor
from almacen.models import Aula, Persona, Prestamo, Producto, Ubicacion

User = get_user_model()


@pytest.mark.django_db
class TestMQTTSimple(TestCase):
    """Prueba simple para creación de préstamo MQTT."""

    def setUp(self):
        """Configurar datos de prueba."""
        # Crear usuario
        self.user = User.objects.create_user(
            username="test_user", email="test@example.com", password="testpass123"
        )

        # Crear aula
        self.aula = Aula.objects.create(nombre="Test Aula")

        # Crear persona
        self.persona, created = Persona.objects.get_or_create(
            user=self.user, defaults={"epc": "PERSONA_EPC_123"}
        )
        if not created:
            self.persona.epc = "PERSONA_EPC_123"
            self.persona.save()

        # Crear producto
        self.product = Producto.objects.create(
            epc="PRODUCT_EPC_001", nombre="Test Product", aula=self.aula
        )

    @patch("almacen.management.commands.mqtt_listener.OPERATION_MODE", "WITH_PERSONA")
    def test_direct_process_producto_epc(self):
        """Prueba llamando directamente al método _process_producto_epc."""
        processor = BatchProcessor(batch_time_seconds=1)

        # Crear ubicación inicial para el producto
        ubicacion = Ubicacion.objects.create(
            producto=self.product, estado="ESTANTE", aula=self.aula
        )

        # Verificar estado inicial - sin préstamos activos
        initial_loans = Prestamo.objects.filter(
            producto=self.product, devuelto_en__isnull=True
        ).count()
        self.assertEqual(initial_loans, 0)

        # Llamar al método directamente
        timestamp = timezone.now()
        processor._process_producto_epc(
            aula_id=self.aula.id,  # type: ignore[attr-defined]
            epc="PRODUCT_EPC_001",
            timestamp=timestamp,
            persona=self.user,
        )

        # Verificar que el préstamo fue creado
        active_loans = Prestamo.objects.filter(
            producto=self.product, devuelto_en__isnull=True
        )
        self.assertEqual(active_loans.count(), 1)

        loan = active_loans.first()
        self.assertEqual(loan.producto, self.product)
        self.assertEqual(loan.usuario, self.user)
        self.assertIsNotNone(loan.tomado_en)

        # Verificar que la Ubicación fue actualizada
        ubicacion.refresh_from_db()
        self.assertEqual(ubicacion.estado, "PERSONA")
        self.assertEqual(ubicacion.persona, self.user)
