"""Tests para la API REST de resolucion EPC-a-nombre."""
import json
import pytest
from django.test import RequestFactory, override_settings
from django.http import JsonResponse
from almacen.api_auth import require_api_key


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
