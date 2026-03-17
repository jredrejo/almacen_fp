"""Tests para la API REST de resolucion EPC-a-nombre."""
import json
import pytest
from django.contrib.auth.models import User
from django.test import Client, RequestFactory, override_settings
from django.http import JsonResponse
from almacen.api_auth import require_api_key
from almacen.models import Aula, Producto, Persona, Prestamo


@pytest.mark.django_db
class TestAPIKeyAuthentication:
    """Pruebas para el decorador require_api_key."""

    def setUp(self):
        """Configurar datos de prueba."""
        self.factory = RequestFactory()

        # Crear vista dummy decorada con require_api_key
        @require_api_key
        def dummy_view(request):
            return JsonResponse({"ok": True})

        self.dummy_view = dummy_view

    @override_settings(API_KEY="test-secret-key")
    def test_request_without_authorization_header_returns_401(self):
        """Prueba que peticion sin header Authorization devuelve 401."""
        self.setUp()
        request = self.factory.get("/api/test/")
        response = self.dummy_view(request)

        assert response.status_code == 401
        assert json.loads(response.content) == {"error": "API key requerida"}

    @override_settings(API_KEY="test-secret-key")
    def test_request_with_wrong_api_key_returns_401(self):
        """Prueba que peticion con API key incorrecta devuelve 401."""
        self.setUp()
        request = self.factory.get("/api/test/", HTTP_AUTHORIZATION="ApiKey wrongkey")
        response = self.dummy_view(request)

        assert response.status_code == 401
        assert json.loads(response.content) == {"error": "API key invalida"}

    @override_settings(API_KEY="test-secret-key")
    def test_request_with_correct_api_key_passes_through(self):
        """Prueba que peticion con API key correcta permite el acceso."""
        self.setUp()
        request = self.factory.get(
            "/api/test/", HTTP_AUTHORIZATION="ApiKey test-secret-key"
        )
        response = self.dummy_view(request)

        assert response.status_code == 200
        assert json.loads(response.content) == {"ok": True}

    @override_settings(API_KEY="test-secret-key")
    def test_request_with_bearer_format_returns_401(self):
        """Prueba que formato incorrecto 'Bearer' devuelve 401."""
        self.setUp()
        request = self.factory.get(
            "/api/test/", HTTP_AUTHORIZATION="Bearer test-secret-key"
        )
        response = self.dummy_view(request)

        assert response.status_code == 401
        assert json.loads(response.content) == {"error": "API key requerida"}

    @override_settings(API_KEY="")
    def test_empty_api_key_rejects_all_requests(self):
        """Prueba que API_KEY vacio rechaza todas las peticiones."""
        self.setUp()
        request = self.factory.get("/api/test/", HTTP_AUTHORIZATION="ApiKey ")
        response = self.dummy_view(request)

        assert response.status_code == 401
        assert json.loads(response.content) == {"error": "API key invalida"}


@pytest.mark.django_db
class TestEPCLookupEndpoints:
    """Pruebas para los endpoints de resolucion EPC."""

    @override_settings(API_KEY="test-secret-key")
    def setUp(self):
        """Configurar datos de prueba."""
        self.client = Client()

        # Crear aula
        self.aula = Aula.objects.create(nombre="Taller Electronica")

        # Crear producto
        self.producto = Producto.objects.create(
            epc="ABC123", nombre="Multimetro Fluke", aula=self.aula
        )

        # Crear producto prestado
        self.usuario = User.objects.create_user(
            username="juan", email="juan@example.com", password="testpass123"
        )
        self.producto_prestado = Producto.objects.create(
            epc="DEF456", nombre="Osciloscopio Tektronix", aula=self.aula
        )
        self.prestamo = Prestamo.objects.create(
            producto=self.producto_prestado, usuario=self.usuario, devuelto_en=None
        )

        # Crear persona con EPC (el signal crea automaticamente la Persona)
        self.usuario_persona = User.objects.create_user(
            username="maria", email="maria@example.com", password="testpass123"
        )
        # Obtener la Persona creada automaticamente y actualizar su EPC
        self.persona = self.usuario_persona.persona
        self.persona.epc = "A1B2C3D4"  # EPC valido (solo hex)
        self.persona.save()

    @override_settings(API_KEY="test-secret-key")
    def test_get_epc_with_producto_returns_producto_data(self):
        """Prueba que GET /api/epc/{epc}/ con EPC de producto devuelve datos completos."""
        self.setUp()
        response = self.client.get(
            "/api/epc/ABC123/",
            HTTP_AUTHORIZATION="ApiKey test-secret-key",
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["epc"] == "ABC123"
        assert data["type"] == "producto"
        assert data["nombre"] == "Multimetro Fluke"
        assert data["aula"] == "Taller Electronica"
        assert data["prestado"] is False
        assert data["prestado_a"] is None

    @override_settings(API_KEY="test-secret-key")
    def test_get_epc_with_producto_prestado_returns_prestamo_status(self):
        """Prueba que producto prestado devuelve estado de prestamo."""
        self.setUp()
        response = self.client.get(
            "/api/epc/DEF456/",
            HTTP_AUTHORIZATION="ApiKey test-secret-key",
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["epc"] == "DEF456"
        assert data["type"] == "producto"
        assert data["nombre"] == "Osciloscopio Tektronix"
        assert data["prestado"] is True
        assert data["prestado_a"] == "juan"  # username

    @override_settings(API_KEY="test-secret-key")
    def test_get_epc_with_persona_returns_persona_data(self):
        """Prueba que GET /api/epc/{epc}/ con EPC de persona devuelve datos de persona."""
        self.setUp()
        response = self.client.get(
            "/api/epc/A1B2C3D4/",
            HTTP_AUTHORIZATION="ApiKey test-secret-key",
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["epc"] == "A1B2C3D4"
        assert data["type"] == "persona"
        assert data["nombre"] == "maria@example.com"  # email cuando no hay full_name

    @override_settings(API_KEY="test-secret-key")
    def test_get_epc_with_unknown_epc_returns_404(self):
        """Prueba que EPC inexistente devuelve 404."""
        self.setUp()
        response = self.client.get(
            "/api/epc/FFFF0000/",  # EPC valido (hex) pero inexistente
            HTTP_AUTHORIZATION="ApiKey test-secret-key",
        )

        assert response.status_code == 404
        data = json.loads(response.content)
        assert data["error"] == "EPC no encontrado"
        assert data["epc"] == "FFFF0000"

    @override_settings(API_KEY="test-secret-key")
    def test_get_epc_with_invalid_format_returns_400(self):
        """Prueba que EPC con formato invalido devuelve 400."""
        self.setUp()
        response = self.client.get(
            "/api/epc/XYZ!!/",
            HTTP_AUTHORIZATION="ApiKey test-secret-key",
        )

        assert response.status_code == 400
        data = json.loads(response.content)
        assert data["error"] == "Formato EPC invalido"
        assert data["epc"] == "XYZ!!"

    @override_settings(API_KEY="test-secret-key")
    def test_get_epc_without_api_key_returns_401(self):
        """Prueba que peticion sin API key devuelve 401."""
        self.setUp()
        response = self.client.get("/api/epc/ABC123/")

        assert response.status_code == 401

    @override_settings(API_KEY="test-secret-key")
    def test_post_bulk_epc_with_valid_epcs_returns_results(self):
        """Prueba que POST /api/epc/ resuelve multiples EPCs."""
        self.setUp()
        response = self.client.post(
            "/api/epc/",
            '{"epcs": ["ABC123", "FFFF0000", "A1B2C3D4"]}',
            content_type="application/json",
            HTTP_AUTHORIZATION="ApiKey test-secret-key",
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "results" in data
        assert len(data["results"]) == 3

        # Primer EPC (producto)
        assert data["results"][0]["epc"] == "ABC123"
        assert data["results"][0]["type"] == "producto"

        # Segundo EPC (desconocido)
        assert data["results"][1]["epc"] == "FFFF0000"
        assert "error" in data["results"][1]

        # Tercer EPC (persona)
        assert data["results"][2]["epc"] == "A1B2C3D4"
        assert data["results"][2]["type"] == "persona"

    @override_settings(API_KEY="test-secret-key")
    def test_post_bulk_epc_with_more_than_50_returns_400(self):
        """Prueba que mas de 50 EPCs devuelve error."""
        self.setUp()
        epcs = [f"EPC{i:03d}" for i in range(51)]
        response = self.client.post(
            "/api/epc/",
            json.dumps({"epcs": epcs}),
            content_type="application/json",
            HTTP_AUTHORIZATION="ApiKey test-secret-key",
        )

        assert response.status_code == 400
        data = json.loads(response.content)
        assert data["error"] == "Maximo 50 EPCs por peticion"
        assert data["enviados"] == 51

    @override_settings(API_KEY="test-secret-key")
    def test_post_bulk_epc_with_invalid_json_returns_400(self):
        """Prueba que JSON invalido devuelve 400."""
        self.setUp()
        response = self.client.post(
            "/api/epc/",
            "invalid json",
            content_type="application/json",
            HTTP_AUTHORIZATION="ApiKey test-secret-key",
        )

        assert response.status_code == 400

    @override_settings(API_KEY="test-secret-key")
    def test_post_bulk_epc_with_non_list_epcs_returns_400(self):
        """Prueba que epcs no siendo lista devuelve 400."""
        self.setUp()
        response = self.client.post(
            "/api/epc/",
            '{"epcs": "no-lista"}',
            content_type="application/json",
            HTTP_AUTHORIZATION="ApiKey test-secret-key",
        )

        assert response.status_code == 400
