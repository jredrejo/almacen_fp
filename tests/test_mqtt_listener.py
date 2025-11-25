"""
Pruebas for MQTT listener command functionality.
Pruebas the BatchProcesaror and EPC processing logic.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from django.core.management import call_command
from django.core.cache import caches
from django.contrib.auth import get_user_model

from almacen.models import Aula, Persona, Producto, Prestamo, Ubicacion
from almacen.management.commands.mqtt_listener import BatchProcessor

User = get_user_model()


@pytest.mark.django_db
class TestMQTTListenerBatchProcessor(TestCase):
    """Prueba la clase BatchProcessor del listener MQTT."""

    def setUp(self):
        """Configurar datos de prueba."""
        # Crear users
        self.staff_user = User.objects.create_user(
            username="test_user", email="test@example.com", password="testpass123"
        )

        # Crear aulas
        self.aula1 = Aula.objects.create(nombre="Aula Test 1")
        self.aula2 = Aula.objects.create(nombre="Aula Test 2")

        # Crear personas (get or create in case signal already created one)
        self.persona, created = Persona.objects.get_or_create(
            user=self.staff_user, defaults={"epc": "PERSONA_EPC_123"}
        )
        if not created:
            # Actualizar EPC if persona was auto-created
            self.persona.epc = "PERSONA_EPC_123"
            self.persona.save()

        # Crear productos
        self.product1 = Producto.objects.create(
            epc="PRODUCT_EPC_001", nombre="Test Product 1", aula=self.aula1
        )
        self.product2 = Producto.objects.create(
            epc="PRODUCT_EPC_002", nombre="Test Product 2", aula=self.aula1
        )

        # Crear cache for testing
        try:
            self.epc_cache = caches["epc_cache"]
        except KeyError:
            self.epc_cache = caches["default"]

    def test_batch_processor_initialization(self):
        """Prueba inicialización de BatchProcessor."""
        processor = BatchProcessor(batch_time_seconds=3)
        self.assertEqual(processor.batch_time, timedelta(seconds=3))
        self.assertEqual(len(processor.batches), 0)
        self.assertEqual(len(processor.last_epc_time), 0)

    def test_add_epc_to_batch(self):
        """Prueba añadir EPCs al lote."""
        processor = BatchProcessor(batch_time_seconds=3)
        timestamp = timezone.now()

        processor.add_epc(self.aula1.id, "EPC_001", timestamp)

        self.assertEqual(len(processor.batches[self.aula1.id]), 1)
        self.assertEqual(processor.batches[self.aula1.id][0], ("EPC_001", timestamp))
        self.assertIn(self.aula1.id, processor.last_epc_time)

    def test_batch_processor_with_expired_batch(self):
        """Prueba procesamiento de lotes expirados."""
        processor = BatchProcessor(batch_time_seconds=1)

        # Añadir EPCs with an old timestamp to simulate expired batch
        old_timestamp = timezone.now() - timedelta(seconds=2)
        processor.add_epc(self.aula1.id, "PERSONA_EPC_123", old_timestamp)
        processor.add_epc(self.aula1.id, "PRODUCT_EPC_001", old_timestamp)

        # Comprobar and process expired batches
        processor.check_and_process_batches()

        # Batch debería ser processed and removed
        self.assertNotIn(self.aula1.id, processor.batches)
        self.assertNotIn(self.aula1.id, processor.last_epc_time)

    @patch("almacen.management.commands.mqtt_listener.OPERATION_MODE", "WITH_PERSONA")
    def test_batch_processing_with_loan_creation(self):
        """Prueba procesamiento por lotes que crea un préstamo."""
        processor = BatchProcessor(batch_time_seconds=1)

        # Añadir persona and product to batch
        timestamp = timezone.now() - timedelta(seconds=2)  # Make it expired
        processor.add_epc(self.aula1.id, "PERSONA_EPC_123", timestamp)
        processor.add_epc(self.aula1.id, "PRODUCT_EPC_001", timestamp)

        # Verificar initial state - no active loans
        initial_loans = Prestamo.objects.filter(
            producto=self.product1, devuelto_en__isnull=True
        ).count()
        self.assertEqual(initial_loans, 0)

        # Procesar the batch
        processor.check_and_process_batches()

        # Verificar loan was created
        active_loans = Prestamo.objects.filter(
            producto=self.product1, devuelto_en__isnull=True
        )
        self.assertEqual(active_loans.count(), 1)

        loan = active_loans.first()
        self.assertEqual(loan.producto, self.product1)
        self.assertEqual(loan.usuario, self.staff_user)
        self.assertIsNotNone(loan.tomado_en)

        # Verificar Ubicacion was updated
        ubicacion = Ubicacion.objects.get(producto=self.product1)
        self.assertEqual(ubicacion.estado, "PERSONA")
        self.assertEqual(ubicacion.persona, self.staff_user)

    @patch("almacen.management.commands.mqtt_listener.OPERATION_MODE", "WITH_PERSONA")
    def test_batch_processing_with_loan_return(self):
        """Prueba procesamiento por lotes que devuelve un préstamo."""
        processor = BatchProcessor(batch_time_seconds=1)

        # Crear an existing active loan
        existing_loan = Prestamo.objects.create(
            producto=self.product1,
            usuario=self.staff_user,
            tomado_en=timezone.now() - timedelta(hours=1),
        )

        # Crear ubicacion for the product
        Ubicacion.objects.create(
            producto=self.product1,
            estado="PERSONA",
            persona=self.staff_user,
            tomado_en=timezone.now() - timedelta(hours=1),
        )

        # Añadir persona and product to batch (return)
        timestamp = timezone.now() - timedelta(seconds=2)  # Make it expired
        processor.add_epc(self.aula1.id, "PERSONA_EPC_123", timestamp)
        processor.add_epc(self.aula1.id, "PRODUCT_EPC_001", timestamp)

        # Procesar the batch
        processor.check_and_process_batches()

        # Verificar loan was marked as returned
        existing_loan.refresh_from_db()
        self.assertIsNotNone(existing_loan.devuelto_en)

        # Verificar Ubicacion was updated
        ubicacion = Ubicacion.objects.get(producto=self.product1)
        self.assertEqual(ubicacion.estado, "ESTANTE")
        self.assertIsNone(ubicacion.persona)

    @patch("almacen.management.commands.mqtt_listener.OPERATION_MODE", "WITH_PERSONA")
    def test_batch_processing_without_persona_creates_error(self):
        """Prueba que el procesamiento por lotes falla cuando no se encuentra persona en modo WITH_PERSONA."""
        processor = BatchProcessor(batch_time_seconds=1)

        # Añadir only product, no persona
        timestamp = timezone.now() - timedelta(seconds=2)  # Make it expired
        processor.add_epc(self.aula1.id, "PRODUCT_EPC_001", timestamp)

        # Procesar the batch - should not create loan
        processor.check_and_process_batches()

        # Verificar no loan was created
        active_loans = Prestamo.objects.filter(
            producto=self.product1, devuelto_en__isnull=True
        )
        self.assertEqual(active_loans.count(), 0)

    @patch(
        "almacen.management.commands.mqtt_listener.OPERATION_MODE", "WITHOUT_PERSONA"
    )
    def test_batch_processing_without_persona_mode(self):
        """Prueba procesamiento por lotes en modo WITHOUT_PERSONA crea préstamos sin usuario."""
        processor = BatchProcessor(batch_time_seconds=1)

        # Añadir only product, no persona
        timestamp = timezone.now() - timedelta(seconds=2)  # Make it expired
        processor.add_epc(self.aula1.id, "PRODUCT_EPC_001", timestamp)

        # Procesar the batch
        processor.check_and_process_batches()

        # Verificar loan was created without user
        active_loans = Prestamo.objects.filter(
            producto=self.product1, devuelto_en__isnull=True
        )
        self.assertEqual(active_loans.count(), 1)

        loan = active_loans.first()
        self.assertEqual(loan.producto, self.product1)
        self.assertIsNone(loan.usuario)  # No user assigned in WITHOUT_PERSONA mode

    def test_batch_processing_unknown_epc(self):
        """Prueba batch processing with unknown EPC doesn't crash."""
        processor = BatchProcessor(batch_time_seconds=1)

        # Añadir unknown EPC
        timestamp = timezone.now() - timedelta(seconds=2)  # Make it expired
        processor.add_epc(self.aula1.id, "UNKNOWN_EPC", timestamp)

        # Procesar the batch - should not crash
        processor.check_and_process_batches()

        # Verificar no loans were created
        active_loans = Prestamo.objects.filter(devuelto_en__isnull=True)
        self.assertEqual(active_loans.count(), 0)

    def test_batch_processing_wrong_ula_assignment(self):
        """Prueba that product in wrong aula gets corrected."""
        processor = BatchProcessor(batch_time_seconds=1)

        # Product is in aula1 but detected in aula2
        timestamp = timezone.now() - timedelta(seconds=2)  # Make it expired
        processor.add_epc(self.aula2.id, "PERSONA_EPC_123", timestamp)
        processor.add_epc(self.aula2.id, "PRODUCT_EPC_001", timestamp)

        # Procesar the batch
        processor.check_and_process_batches()

        # Verificar product was moved to correct aula
        self.product1.refresh_from_db()
        self.assertEqual(self.product1.aula, self.aula2)


@pytest.mark.django_db
class TestMQTTListenerCommand(TestCase):
    """Prueba the MQTT listener management command."""

    def setUp(self):
        """Configurar datos de prueba."""
        self.aula = Aula.objects.create(nombre="Test Aula")

    def test_command_initialization(self):
        """Prueba that the command can be initialized."""
        # Prueba that the command exists and can be imported
        from almacen.management.commands.mqtt_listener import Command

        command = Command()
        self.assertIsNotNone(command)
        self.assertEqual(
            command.help,
            "Escucha mensajes MQTT para EPC de RFID con proceso por lotes.",
        )
