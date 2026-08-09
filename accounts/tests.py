from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import User


class RegisterViewTests(APITestCase):
    """Covers the registration behaviours documented as 'Verified working' in README.md."""

    def setUp(self):
        self.url = reverse("register")

    def valid_payload(self, **overrides):
        payload = {
            "email": "jane@example.com",
            "full_name": "Jane Doe",
            "password": "Health123",
            "password_confirm": "Health123",
            "privacy_consent": True,
        }
        payload.update(overrides)
        return payload

    def test_register_creates_user_and_returns_tokens(self):
        response = self.client.post(self.url, self.valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        user = User.objects.get(email="jane@example.com")
        self.assertIsNotNone(user.privacy_consent_at)

    def test_register_rejects_password_under_eight_characters(self):
        response = self.client.post(self.url, self.valid_payload(
            password="Ab1", password_confirm="Ab1"), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_register_rejects_password_with_no_digit(self):
        response = self.client.post(self.url, self.valid_payload(
            password="NoDigitsHere", password_confirm="NoDigitsHere"), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_register_rejects_mismatched_password_confirmation(self):
        response = self.client.post(self.url, self.valid_payload(
            password_confirm="SomethingElse1"), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", response.data)

    def test_register_rejects_duplicate_email(self):
        User.objects.create_user(email="jane@example.com", password="Health123")

        response = self.client.post(self.url, self.valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_register_rejects_missing_privacy_consent(self):
        response = self.client.post(self.url, self.valid_payload(
            privacy_consent=False), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("privacy_consent", response.data)


class NotesEndpointAuthTests(APITestCase):
    """Confirms the documented 401 behaviour for unauthenticated note access."""

    def test_unauthenticated_request_to_notes_returns_401(self):
        response = self.client.get("/api/v1/notes/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
