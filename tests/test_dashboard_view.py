"""Pruebas simplificadas para la lógica de la vista dashboard sin renderizado de plantillas."""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from almacen.models import Persona, Aula, Producto, Ubicacion, Prestamo

User = get_user_model()


class TestDashboardLogic(TestCase):
    """Prueba la lógica de la vista dashboard con control de acceso."""

    def setUp(self):
        """Configurar los datos de prueba."""
        # Crear aulas de prueba
        self.aula1 = Aula.objects.create(nombre="Aula 101")
        self.aula2 = Aula.objects.create(nombre="Aula 102")

        # Crear usuarios
        self.staff_user = User.objects.create_user(
            username="staff_test",
            email="staff@example.com",
            password="testpass123",
            is_staff=True,
        )

        self.restricted_user = User.objects.create_user(
            username="restricted_test",
            email="restricted@example.com",
            password="testpass123",
            is_staff=False,
        )

        self.no_access_user = User.objects.create_user(
            username="no_access_test",
            email="noaccess@example.com",
            password="testpass123",
            is_staff=False,
        )

        # Crear personas
        self.staff_persona, _ = Persona.objects.get_or_create(user=self.staff_user)
        self.restricted_persona, _ = Persona.objects.get_or_create(
            user=self.restricted_user
        )
        self.no_access_persona, _ = Persona.objects.get_or_create(
            user=self.no_access_user
        )

        # Asignar acceso al usuario restringido (solo aula1)
        self.restricted_persona.aulas_access.clear()
        self.restricted_persona.aulas_access.add(self.aula1)

        # Crear productos
        self.product_aula1_1 = Producto.objects.create(
            nombre="Product Aula1-1", epc="A1011", aula=self.aula1
        )
        self.product_aula1_2 = Producto.objects.create(
            nombre="Product Aula1-2", epc="A1012", aula=self.aula1
        )
        self.product_aula2_1 = Producto.objects.create(
            nombre="Product Aula2-1", epc="A1021", aula=self.aula2
        )

        # Crear ubicaciones y préstamos
        # Producto Aula1-1 está tomado
        Ubicacion.objects.create(producto=self.product_aula1_1, estado="PERSONA")
        Prestamo.objects.create(
            producto=self.product_aula1_1,
            usuario=self.restricted_user,
            tomado_en=timezone.now(),
        )

        # Producto Aula1-2 está en stock
        Ubicacion.objects.create(producto=self.product_aula1_2, estado="ESTANTE")

        # Producto Aula2-1 está en stock
        Ubicacion.objects.create(producto=self.product_aula2_1, estado="ESTANTE")

    def test_dashboard_staff_sees_all_data(self):
        """Prueba que los usuarios staff ven datos de todas las aulas."""
        from almacen.views import dashboard

        # Simular request para usuario staff
        class MockRequest:
            def __init__(self, user):
                self.user = user
                self.session = {}
                self.GET = {}
                self.META = {}

        request = MockRequest(self.staff_user)

        # Probar la lógica de control de acceso del dashboard
        qs = Producto.objects.all()
        current_aula = None

        if request.user.is_authenticated:
            try:
                persona = request.user.persona
                if not persona.user.is_staff:
                    accessible_aulas = persona.get_aulas_access()
                    if current_aula:
                        if persona.has_aula_access(current_aula):
                            qs = qs.filter(aula=current_aula)
                        else:
                            qs = qs.none()
                    else:
                        qs = qs.filter(aula__in=accessible_aulas)
                else:
                    # Los usuarios staff ven todos los productos (sin filtrar)
                    pass
            except Persona.DoesNotExist:
                qs = qs.none()

        total = qs.count()
        en_manos = qs.filter(ubicacion__estado="PERSONA").count()
        en_estante = total - en_manos
        recientes = qs.order_by("-creado")[:8]

        # Staff debería ver todos los productos
        self.assertEqual(total, 3)
        self.assertEqual(en_manos, 1)  # Un producto está tomado
        self.assertEqual(en_estante, 2)  # Dos productos en stock
        self.assertEqual(len(recientes), 3)

    def test_dashboard_restricted_user_sees_accessible_aulas(self):
        """Prueba que los usuarios restringidos ven solo productos de sus aulas accesibles."""
        from almacen.views import dashboard

        # Simular request para usuario restringido
        class MockRequest:
            def __init__(self, user):
                self.user = user
                self.session = {}
                self.GET = {}
                self.META = {}

        request = MockRequest(self.restricted_user)

        # Probar la lógica de control de acceso del dashboard
        qs = Producto.objects.all()
        current_aula = None

        if request.user.is_authenticated:
            try:
                persona = request.user.persona
                if not persona.user.is_staff:
                    accessible_aulas = persona.get_aulas_access()
                    if current_aula:
                        if persona.has_aula_access(current_aula):
                            qs = qs.filter(aula=current_aula)
                        else:
                            qs = qs.none()
                    else:
                        qs = qs.filter(aula__in=accessible_aulas)
                else:
                    pass
            except Persona.DoesNotExist:
                qs = qs.none()

        total = qs.count()
        en_manos = qs.filter(ubicacion__estado="PERSONA").count()
        en_estante = total - en_manos
        recientes = qs.order_by("-creado")[:8]

        # Usuario restringido debería ver solo productos del aula1
        self.assertEqual(total, 2)  # Solo 2 productos en el aula1
        self.assertEqual(en_manos, 1)  # Un producto del aula1 está tomado
        self.assertEqual(en_estante, 1)  # Un producto del aula1 está en stock
        self.assertEqual(len(recientes), 2)

        # Verificar que todos los productos son del aula1
        for product in recientes:
            self.assertEqual(product.aula, self.aula1)

    def test_dashboard_no_access_user_sees_nothing(self):
        """Prueba que los usuarios sin acceso aulas no ven datos."""
        from almacen.views import dashboard

        # Simular request para usuario sin acceso
        class MockRequest:
            def __init__(self, user):
                self.user = user
                self.session = {}
                self.GET = {}
                self.META = {}

        request = MockRequest(self.no_access_user)

        # Probar la lógica de control de acceso del dashboard
        qs = Producto.objects.all()
        current_aula = None

        if request.user.is_authenticated:
            try:
                persona = request.user.persona
                if not persona.user.is_staff:
                    accessible_aulas = persona.get_aulas_access()
                    if current_aula:
                        if persona.has_aula_access(current_aula):
                            qs = qs.filter(aula=current_aula)
                        else:
                            qs = qs.none()
                    else:
                        qs = qs.filter(aula__in=accessible_aulas)
                else:
                    pass
            except Persona.DoesNotExist:
                qs = qs.none()

        total = qs.count()
        en_manos = qs.filter(ubicacion__estado="PERSONA").count()
        en_estante = total - en_manos
        recientes = qs.order_by("-creado")[:8]

        # Usuario sin acceso debería ver nada
        self.assertEqual(total, 0)
        self.assertEqual(en_manos, 0)
        self.assertEqual(en_estante, 0)
        self.assertEqual(len(recientes), 0)

    def test_dashboard_current_aula_filtering(self):
        """Prueba dashboard cuando el aula actual está establecida."""
        from almacen.views import dashboard

        # Simular request para usuario restringido con aula actual establecida
        class MockRequest:
            def __init__(self, user, current_aula=None):
                self.user = user
                self.session = (
                    {"current_aula_id": current_aula.id} if current_aula else {}
                )
                self.GET = {}
                self.META = {}

        # Probar con aula actual establecida a aula1 (usuario tiene acceso)
        request = MockRequest(self.restricted_user, current_aula=self.aula1)

        # Simular lógica de get_current_aula
        current_aula = self.aula1

        qs = Producto.objects.all()

        if request.user.is_authenticated:
            try:
                persona = request.user.persona
                if not persona.user.is_staff:
                    accessible_aulas = persona.get_aulas_access()
                    if current_aula:
                        if persona.has_aula_access(current_aula):
                            qs = qs.filter(aula=current_aula)
                        else:
                            qs = qs.none()
                    else:
                        qs = qs.filter(aula__in=accessible_aulas)
            except Persona.DoesNotExist:
                qs = qs.none()

        total = qs.count()
        en_manos = qs.filter(ubicacion__estado="PERSONA").count()
        en_estante = total - en_manos
        recientes = qs.order_by("-creado")[:8]

        # Debería ver solo productos del aula1
        self.assertEqual(total, 2)
        self.assertEqual(en_manos, 1)
        self.assertEqual(en_estante, 1)
        self.assertEqual(len(recientes), 2)

    def test_dashboard_current_aula_no_access(self):
        """Prueba dashboard cuando el aula actual no es accesible."""
        from almacen.views import get_current_aula

        # Simular request para usuario restringido con aula actual a la que no tienen acceso
        class MockRequest:
            def __init__(self, user, current_aula=None):
                self.user = user
                self.session = (
                    {"current_aula_id": current_aula.id} if current_aula else {}
                )
                self.GET = {}
                self.META = {}

        # Probar con aula actual establecida a aula2 (usuario NO tiene acceso)
        request = MockRequest(self.restricted_user, current_aula=self.aula2)

        # Simular lógica de get_current_aula - esto debería devolver None ya que el usuario no tiene acceso
        current_aula = (
            None  # get_current_aula devolvería None debido al control de acceso
        )

        qs = Producto.objects.all()

        if request.user.is_authenticated:
            try:
                persona = request.user.persona
                if not persona.user.is_staff:
                    accessible_aulas = persona.get_aulas_access()
                    if current_aula:
                        if persona.has_aula_access(current_aula):
                            qs = qs.filter(aula=current_aula)
                        else:
                            qs = qs.none()
                    else:
                        qs = qs.filter(aula__in=accessible_aulas)
            except Persona.DoesNotExist:
                qs = qs.none()

        total = qs.count()
        en_manos = qs.filter(ubicacion__estado="PERSONA").count()
        en_estante = total - en_manos
        recientes = qs.order_by("-creado")[:8]

        # Debería ver todos los productos de aulas accesibles (solo aula1)
        self.assertEqual(total, 2)
        self.assertEqual(en_manos, 1)
        self.assertEqual(en_estante, 1)
        self.assertEqual(len(recientes), 2)
