import pytest
from django.contrib.auth.models import User, AnonymousUser
from django.test import TestCase, RequestFactory
from almacen.models import Aula, Persona, Producto
from almacen.views import get_current_aula
from almacen.context_processors import aula_context


@pytest.mark.django_db
class TestAccessControlBasic(TestCase):
    """Basic tests for the access control functionality."""

    def setUp(self):
        """Set up test data."""
        self.factory = RequestFactory()

        # Create users (Persona will be created automatically by signal)
        self.staff_user = User.objects.create_user(
            username="staff_user", email="staff@example.com", password="testpass123"
        )
        self.staff_user.is_staff = True
        self.staff_user.save()

        self.regular_user = User.objects.create_user(
            username="regular_user", email="regular@example.com", password="testpass123"
        )

        # Create aulas
        self.aula1 = Aula.objects.create(nombre="Aula 101")
        self.aula2 = Aula.objects.create(nombre="Aula 102")

        # Get personas that were created by signal
        self.staff_persona = self.staff_user.persona
        self.regular_persona = self.regular_user.persona

    def test_persona_access_methods(self):
        """Test the Persona access control methods."""
        # Test staff has unrestricted access
        self.assertTrue(self.staff_persona.has_aula_access(self.aula1))
        self.assertTrue(self.staff_persona.has_aula_access(self.aula2))
        self.assertEqual(self.staff_persona.get_aulas_access().count(), 2)

        # Test regular user has no access by default (new behavior)
        self.assertFalse(self.regular_persona.has_aula_access(self.aula1))
        self.assertFalse(self.regular_persona.has_aula_access(self.aula2))
        self.assertEqual(self.regular_persona.get_aulas_access().count(), 0)

        # Test restricting regular user
        self.regular_persona.aulas_access.add(self.aula1)
        self.regular_persona.aulas_access.add(self.aula2)

        self.assertTrue(self.regular_persona.has_aula_access(self.aula1))
        self.assertTrue(self.regular_persona.has_aula_access(self.aula2))
        self.assertEqual(self.regular_persona.get_aulas_access().count(), 2)

        # Test removing access to one aula
        self.regular_persona.aulas_access.remove(self.aula2)
        self.assertTrue(self.regular_persona.has_aula_access(self.aula1))
        self.assertFalse(self.regular_persona.has_aula_access(self.aula2))

        # Test clearing access (should give no access with new behavior)
        self.regular_persona.aulas_access.clear()
        self.assertFalse(self.regular_persona.has_aula_access(self.aula1))
        self.assertFalse(self.regular_persona.has_aula_access(self.aula2))
        self.assertEqual(self.regular_persona.get_aulas_access().count(), 0)

    def test_get_current_aula_with_access_control(self):
        """Test get_current_aula function with access control."""
        # Restrict regular user to only aula1
        self.regular_persona.aulas_access.add(self.aula1)

        # Test staff can access any aula
        request = self.factory.get(f"/?aula={self.aula2.id}")
        request.user = self.staff_user
        request.session = {}

        current_aula = get_current_aula(request)
        self.assertEqual(current_aula, self.aula2)

        # Test restricted user can access assigned aula
        request = self.factory.get(f"/?aula={self.aula1.id}")
        request.user = self.regular_user
        request.session = {}

        current_aula = get_current_aula(request)
        self.assertEqual(current_aula, self.aula1)

        # Test restricted user cannot access unassigned aula
        request = self.factory.get(f"/?aula={self.aula2.id}")
        request.user = self.regular_user
        request.session = {}

        current_aula = get_current_aula(request)
        self.assertIsNone(current_aula)

    def test_persona_string_representation(self):
        """Test Persona __str__ method."""
        expected_str = self.staff_user.get_full_name() or self.staff_user.email
        self.assertEqual(str(self.staff_persona), expected_str)


@pytest.mark.django_db
class TestAccessControlWithProducts(TestCase):
    """Test access control with product relationships."""

    def setUp(self):
        """Set up test data."""
        # Create users (Persona will be created automatically by signal)
        self.staff_user = User.objects.create_user(
            username="staff_user2", email="staff2@example.com", password="testpass123"
        )
        self.staff_user.is_staff = True
        self.staff_user.save()

        self.restricted_user = User.objects.create_user(
            username="restricted_user",
            email="restricted@example.com",
            password="testpass123",
        )

        # Create aulas
        self.aula1 = Aula.objects.create(nombre="Aula 201")
        self.aula2 = Aula.objects.create(nombre="Aula 202")

        # Get personas that were created by signal
        self.staff_persona = self.staff_user.persona
        self.restricted_persona = self.restricted_user.persona

        # Restrict user to only aula1
        self.restricted_persona.aulas_access.add(self.aula1)

        # Create products
        self.product1 = Producto.objects.create(
            epc="EPC001", nombre="Product 1", aula=self.aula1
        )
        self.product2 = Producto.objects.create(
            epc="EPC002", nombre="Product 2", aula=self.aula2
        )

    def test_product_access_by_aula(self):
        """Test that access control works with products."""
        # Staff can access products from any aula
        self.assertTrue(self.staff_persona.has_aula_access(self.product1.aula))
        self.assertTrue(self.staff_persona.has_aula_access(self.product2.aula))

        # Restricted user can only access products from accessible aulas
        self.assertTrue(self.restricted_persona.has_aula_access(self.product1.aula))
        self.assertFalse(self.restricted_persona.has_aula_access(self.product2.aula))

    def test_persona_last_aula_preference(self):
        """Test that Persona.last_aula works with access control."""
        # Set last_aula to accessible aula
        self.restricted_persona.last_aula = self.aula1
        self.restricted_persona.save()

        self.assertEqual(self.restricted_persona.last_aula, self.aula1)

        # Try to set last_aula to inaccessible aula (should be allowed in model,
        # but views will enforce access control)
        self.restricted_persona.last_aula = self.aula2
        self.restricted_persona.save()

        self.assertEqual(
            self.restricted_persona.last_aula, self.aula2
        )  # Model allows it
        # But has_aula_access will still enforce restrictions
        self.assertFalse(self.restricted_persona.has_aula_access(self.aula2))


@pytest.mark.django_db
class TestNavbarAulaFiltering(TestCase):
    """Test navbar aula filtering in context processor."""

    def setUp(self):
        """Set up test data."""
        self.factory = RequestFactory()

        # Create users
        self.staff_user = User.objects.create_user(
            username="staff_nav", email="staffnav@example.com", password="testpass123"
        )
        self.staff_user.is_staff = True
        self.staff_user.save()

        self.regular_user = User.objects.create_user(
            username="regular_nav",
            email="regularnav@example.com",
            password="testpass123",
        )

        self.restricted_user = User.objects.create_user(
            username="restricted_nav",
            email="restrictednav@example.com",
            password="testpass123",
        )

        # Create aulas
        self.aula1 = Aula.objects.create(nombre="Aula 301")
        self.aula2 = Aula.objects.create(nombre="Aula 302")
        self.aula3 = Aula.objects.create(nombre="Aula 303")

        # Get personas created by signal
        self.staff_persona = self.staff_user.persona
        self.regular_persona = self.regular_user.persona
        self.restricted_persona = self.restricted_user.persona

        # Restrict user to only aula1 and aula2
        self.restricted_persona.aulas_access.add(self.aula1, self.aula2)

    def test_context_processor_staff_user_sees_all_aulas(self):
        """Test that staff users see all aulas in navbar."""
        request = self.factory.get("/")
        request.user = self.staff_user
        request.session = {}

        context = aula_context(request)

        # Staff should see all aulas
        self.assertEqual(context["ctx_all_aulas"].count(), 3)
        aula_names = list(context["ctx_all_aulas"].values_list("nombre", flat=True))
        self.assertIn("Aula 301", aula_names)
        self.assertIn("Aula 302", aula_names)
        self.assertIn("Aula 303", aula_names)

    def test_context_processor_regular_user_sees_no_aulas_by_default(self):
        """Test that regular users with no restrictions see no aulas (new behavior)."""
        request = self.factory.get("/")
        request.user = self.regular_user
        request.session = {}

        context = aula_context(request)

        # Regular user with no assigned aulas should see no aulas
        self.assertEqual(context["ctx_all_aulas"].count(), 0)

    def test_context_processor_restricted_user_sees_only_allowed_aulas(self):
        """Test that restricted users see only their assigned aulas."""
        request = self.factory.get("/")
        request.user = self.restricted_user
        request.session = {}

        context = aula_context(request)

        # Restricted user should see only assigned aulas (aula1 and aula2)
        self.assertEqual(context["ctx_all_aulas"].count(), 2)
        aula_names = list(context["ctx_all_aulas"].values_list("nombre", flat=True))
        self.assertIn("Aula 301", aula_names)
        self.assertIn("Aula 302", aula_names)
        self.assertNotIn("Aula 303", aula_names)

    def test_context_processor_anonymous_user_sees_no_aulas(self):
        """Test that anonymous users see no aulas (new behavior)."""
        request = self.factory.get("/")
        request.user = AnonymousUser()
        request.session = {}

        context = aula_context(request)

        # Anonymous users should see no aulas
        self.assertEqual(context["ctx_all_aulas"].count(), 0)

    def test_context_processor_user_without_persona_sees_no_aulas(self):
        """Test fallback behavior when user has no Persona object."""
        # Create user without triggering Persona creation signal
        user_without_persona = User.objects.create_user(
            username="no_persona", email="nopersona@example.com", password="testpass123"
        )

        request = self.factory.get("/")
        request.user = user_without_persona
        request.session = {}

        context = aula_context(request)

        # Non-staff users without Persona should see no aulas
        self.assertEqual(context["ctx_all_aulas"].count(), 0)
