"""
Simple test to verify the MQTT listener loan creation logic.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from almacen.models import Aula, Persona, Producto, Prestamo, Ubicacion
from almacen.management.commands.mqtt_listener import BatchProcessor

User = get_user_model()


@pytest.mark.django_db
class TestMQTTSimple(TestCase):
    """Simple test for MQTT loan creation."""

    def setUp(self):
        """Set up test data."""
        # Create user
        self.user = User.objects.create_user(
            username="test_user", email="test@example.com", password="testpass123"
        )

        # Create aula
        self.aula = Aula.objects.create(nombre="Test Aula")

        # Create persona
        self.persona, created = Persona.objects.get_or_create(
            user=self.user, defaults={"epc": "PERSONA_EPC_123"}
        )
        if not created:
            self.persona.epc = "PERSONA_EPC_123"
            self.persona.save()

        # Create product
        self.product = Producto.objects.create(
            epc="PRODUCT_EPC_001", nombre="Test Product", aula=self.aula
        )

    @patch("almacen.management.commands.mqtt_listener.OPERATION_MODE", "WITH_PERSONA")
    def test_direct_process_producto_epc(self):
        """Test directly calling _process_producto_epc method."""
        processor = BatchProcessor(batch_time_seconds=1)

        # Create initial ubicacion for the product
        ubicacion = Ubicacion.objects.create(
            producto=self.product, estado="ESTANTE", aula=self.aula
        )

        # Verify initial state - no active loans
        initial_loans = Prestamo.objects.filter(
            producto=self.product, devuelto_en__isnull=True
        ).count()
        self.assertEqual(initial_loans, 0)

        # Call the method directly
        timestamp = timezone.now()
        processor._process_producto_epc(
            aula_id=self.aula.id,
            epc="PRODUCT_EPC_001",
            timestamp=timestamp,
            persona=self.user,
        )

        # Verify loan was created
        active_loans = Prestamo.objects.filter(
            producto=self.product, devuelto_en__isnull=True
        )
        self.assertEqual(active_loans.count(), 1)

        loan = active_loans.first()
        self.assertEqual(loan.producto, self.product)
        self.assertEqual(loan.usuario, self.user)
        self.assertIsNotNone(loan.tomado_en)

        # Verify Ubicacion was updated
        ubicacion.refresh_from_db()
        self.assertEqual(ubicacion.estado, "PERSONA")
        self.assertEqual(ubicacion.persona, self.user)
