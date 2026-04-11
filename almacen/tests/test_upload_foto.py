import io
from django.conf import settings
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from almacen.models import Aula, FotoRFID

JPEG_MAGIC = b"\xff\xd8\xff"
VALID_JPEG = JPEG_MAGIC + b"\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 100
# ^ good-enough bytes: starts with FF D8 FF, passes the view's magic check.
# Pillow may reject it inside ImageField.save if we ever toggle strict validation;
# current view does NOT call Pillow explicitly, so ContentFile will save the blob verbatim.


@override_settings(SECURE_SSL_REDIRECT=False)
class UploadFotoTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse("api_upload_foto")
        self.api_key = settings.API_KEY
        self.aula = Aula.objects.create(nombre="Test Aula 1")

    def _post(self, body=VALID_JPEG, filename="ABCD1234_2026-04-11_10-30-00.jpg",
              aula_id=None, api_key=None):
        headers = {"HTTP_AUTHORIZATION": f"ApiKey {api_key or self.api_key}"}
        if filename is not None:
            headers["HTTP_X_FILENAME"] = filename
        if aula_id is not None:
            headers["HTTP_X_AULA_ID"] = str(aula_id)
        return self.client.post(
            self.url, data=body, content_type="image/jpeg", **headers
        )

    def test_happy_path_creates_fotorfid(self):
        r = self._post(aula_id=self.aula.id)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(FotoRFID.objects.count(), 1)
        row = FotoRFID.objects.first()
        self.assertEqual(row.epc, "ABCD1234")
        self.assertEqual(row.aula_id, self.aula.id)
        self.assertEqual(row.tamano_bytes, len(VALID_JPEG))

    def test_missing_api_key_returns_401(self):
        r = self.client.post(self.url, data=VALID_JPEG, content_type="image/jpeg",
                             HTTP_X_FILENAME="ABCD1234_2026-04-11_10-30-00.jpg")
        self.assertEqual(r.status_code, 401)

    def test_wrong_api_key_returns_401(self):
        r = self._post(api_key="wrong-key")
        self.assertEqual(r.status_code, 401)

    def test_get_method_returns_405(self):
        r = self.client.get(self.url, HTTP_AUTHORIZATION=f"ApiKey {self.api_key}")
        self.assertEqual(r.status_code, 405)

    def test_path_traversal_filename_rejected(self):
        r = self._post(filename="../etc/passwd.jpg")
        self.assertEqual(r.status_code, 400)

    def test_non_hex_epc_rejected(self):
        r = self._post(filename="NOTHEXXG_2026-04-11_10-30-00.jpg")
        self.assertEqual(r.status_code, 400)

    def test_missing_filename_rejected(self):
        r = self._post(filename=None)
        self.assertEqual(r.status_code, 400)

    def test_invalid_timestamp_rejected(self):
        r = self._post(filename="ABCD1234_2026-13-01_10-30-00.jpg")
        self.assertEqual(r.status_code, 400)

    def test_not_jpeg_body_rejected(self):
        r = self._post(body=b"this is not a jpeg" + b"\x00" * 50)
        self.assertEqual(r.status_code, 400)

    def test_empty_body_rejected(self):
        r = self._post(body=b"")
        self.assertEqual(r.status_code, 400)

    def test_oversized_body_rejected(self):
        big = JPEG_MAGIC + b"\x00" * (10 * 1024 * 1024 + 1)
        r = self._post(body=big)
        self.assertEqual(r.status_code, 413)

    def test_duplicate_is_idempotent(self):
        r1 = self._post(aula_id=self.aula.id)
        r2 = self._post(aula_id=self.aula.id)
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 200)
        import json
        self.assertTrue(json.loads(r2.content)["duplicate"])
        self.assertEqual(FotoRFID.objects.count(), 1)

    def test_unknown_aula_saves_null(self):
        r = self._post(aula_id=9999)
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(FotoRFID.objects.first().aula)

    def test_timestamp_is_madrid_local(self):
        r = self._post(aula_id=self.aula.id)
        self.assertEqual(r.status_code, 201)
        ts = FotoRFID.objects.first().timestamp_captura
        self.assertIsNotNone(ts.tzinfo)
        # Django USE_TZ=True stores as UTC; verify the timestamp value is correct
        # by converting back to Madrid local time and checking the wall clock.
        from zoneinfo import ZoneInfo
        madrid = ZoneInfo("Europe/Madrid")
        local = ts.astimezone(madrid)
        self.assertEqual(local.hour, 10)
        self.assertEqual(local.minute, 30)
        self.assertEqual(local.second, 0)
