"""Tests E2E del contrato MQTT: lectura simulada -> persistencia Django (TEST-01)."""

import json
import pytest
from collections import Counter
from datetime import timedelta
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from almacen.models import (
    Aula,
    LecturaHuerfana,
    Persona,
    Prestamo,
    Producto,
    Ubicacion,
)
from almacen.management.commands.mqtt_listener import Command, BatchProcessor

User = get_user_model()


def _make_msg(aula_id, epc, timestamp_str):
    """Build a mock MQTT message for rfid/lectura/{aula_id}."""
    msg = MagicMock()
    msg.topic = f"rfid/lectura/{aula_id}"
    msg.payload = json.dumps({
        "aula_id": str(aula_id),
        "epc": epc,
        "timestamp": timestamp_str,
    }).encode("utf-8")
    return msg


@pytest.mark.django_db
@pytest.mark.contract
class TestContractMQTTE2E:
    """E2E contract tests: MQTT lectura message -> Django persistence."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="e2e_user", email="e2e@example.com", password="testpass123"
        )
        self.aula = Aula.objects.create(
            nombre="Aula E2E", operation_mode="WITH_PERSONA"
        )
        # Auto-created Persona via signal; update EPC to valid hex
        self.persona = self.user.persona
        self.persona.epc = "AAAA0000BBBB1111"
        self.persona.save()

        self.producto = Producto.objects.create(
            epc="CCCC0000DDDD2222", nombre="Multimetro E2E", aula=self.aula
        )

        self.command = Command()
        self.command.batch_processor = BatchProcessor(batch_time_seconds=1)
        self.command.reject_counts = Counter()

    @override_settings(SECURE_SSL_REDIRECT=False)
    def test_e2e_prestamo_creation(self):
        """Persona+Producto EPCs -> Prestamo created, Ubicacion=PERSONA."""
        self.setUp()
        ts_str = "2026-04-14T10:30:00Z"
        self.command.on_message(
            client=MagicMock(), userdata=None,
            msg=_make_msg(self.aula.pk, "AAAA0000BBBB1111", ts_str),
        )
        self.command.on_message(
            client=MagicMock(), userdata=None,
            msg=_make_msg(self.aula.pk, "CCCC0000DDDD2222", ts_str),
        )
        # Force batch expiry
        self.command.batch_processor.last_epc_time[self.aula.pk] = (
            timezone.now() - timedelta(seconds=2)
        )
        self.command.batch_processor.check_and_process_batches()

        assert Prestamo.objects.filter(
            producto=self.producto, devuelto_en__isnull=True
        ).count() == 1
        ubi = Ubicacion.objects.get(producto=self.producto)
        assert ubi.estado == "PERSONA"
        assert ubi.persona == self.user

    @override_settings(SECURE_SSL_REDIRECT=False)
    def test_e2e_unknown_epc_creates_lectura_huerfana(self):
        """Unknown EPC -> LecturaHuerfana persisted (WITH_PERSONA + persona in batch)."""
        self.setUp()
        ts_str = "2026-04-14T11:00:00Z"
        # Send persona first so the batch has a persona present
        self.command.on_message(
            client=MagicMock(), userdata=None,
            msg=_make_msg(self.aula.pk, "AAAA0000BBBB1111", ts_str),
        )
        # Send unknown EPC -- not in Producto nor Persona
        self.command.on_message(
            client=MagicMock(), userdata=None,
            msg=_make_msg(self.aula.pk, "AAFF00112233DEAD", ts_str),
        )
        self.command.batch_processor.last_epc_time[self.aula.pk] = (
            timezone.now() - timedelta(seconds=2)
        )
        self.command.batch_processor.check_and_process_batches()

        assert LecturaHuerfana.objects.filter(epc="AAFF00112233DEAD").count() == 1
        lh = LecturaHuerfana.objects.get(epc="AAFF00112233DEAD")
        assert lh.aula_id == self.aula.pk

    @override_settings(SECURE_SSL_REDIRECT=False)
    def test_e2e_invalid_payload_rejected(self):
        """Invalid EPC format -> rejected, no DB side-effects."""
        self.setUp()
        ts_str = "2026-04-14T12:00:00Z"
        # Build msg with invalid EPC "ZZZZ" directly
        msg = MagicMock()
        msg.topic = f"rfid/lectura/{self.aula.pk}"
        msg.payload = json.dumps({
            "aula_id": str(self.aula.pk),
            "epc": "ZZZZ",
            "timestamp": ts_str,
        }).encode("utf-8")

        self.command.on_message(client=MagicMock(), userdata=None, msg=msg)

        assert self.command.reject_counts["epc_format"] >= 1
        assert LecturaHuerfana.objects.count() == 0
        assert Prestamo.objects.count() == 0

    @override_settings(SECURE_SSL_REDIRECT=False)
    def test_e2e_aula_mismatch_rejected(self):
        """Topic aula_id != payload aula_id -> rejected."""
        self.setUp()
        ts_str = "2026-04-14T13:00:00Z"
        msg = MagicMock()
        msg.topic = f"rfid/lectura/999"
        msg.payload = json.dumps({
            "aula_id": str(self.aula.pk),
            "epc": "AABBCCDDEEFF0011",
            "timestamp": ts_str,
        }).encode("utf-8")

        self.command.on_message(client=MagicMock(), userdata=None, msg=msg)

        assert self.command.reject_counts["aula_mismatch"] >= 1

    @override_settings(SECURE_SSL_REDIRECT=False)
    def test_e2e_devolucion(self):
        """Scanning already-borrowed product -> Prestamo closed, Ubicacion=ESTANTE."""
        self.setUp()
        # Create existing active loan
        now = timezone.now()
        Prestamo.objects.create(
            producto=self.producto, usuario=self.user, tomado_en=now
        )
        Ubicacion.objects.create(
            producto=self.producto, estado="PERSONA", persona=self.user,
            tomado_en=now,
        )

        ts_str = "2026-04-14T14:00:00Z"
        self.command.on_message(
            client=MagicMock(), userdata=None,
            msg=_make_msg(self.aula.pk, "AAAA0000BBBB1111", ts_str),
        )
        self.command.on_message(
            client=MagicMock(), userdata=None,
            msg=_make_msg(self.aula.pk, "CCCC0000DDDD2222", ts_str),
        )
        self.command.batch_processor.last_epc_time[self.aula.pk] = (
            timezone.now() - timedelta(seconds=2)
        )
        self.command.batch_processor.check_and_process_batches()

        assert Prestamo.objects.filter(
            producto=self.producto, devuelto_en__isnull=True
        ).count() == 0
        ubi = Ubicacion.objects.get(producto=self.producto)
        assert ubi.estado == "ESTANTE"
