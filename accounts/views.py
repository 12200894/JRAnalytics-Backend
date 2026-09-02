from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import PasswordResetCode
from .serializers import (ChangePasswordSerializer, PasswordResetConfirmSerializer,
                           PasswordResetRequestSerializer, RegisterSerializer, UserSerializer)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """POST /api/v1/auth/register/ — creates an account and returns a token pair."""
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            "user": UserSerializer(user).data,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }, status=status.HTTP_201_CREATED)


class ProfileView(generics.RetrieveUpdateAPIView):
    """GET / PATCH /api/v1/auth/me/ — always scoped to the caller."""
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    """POST /api/v1/auth/change-password/ — verifies current_password, then sets new_password."""

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password updated."})


class DeleteAccountView(generics.DestroyAPIView):
    """
    DELETE /api/v1/auth/me/delete/ — permanently deletes the caller's account.

    HealthNote and AISummary both cascade off the user FK, so this also removes every
    note, attachment and summary the account ever created. No soft-delete: gone is gone.
    """
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

    def destroy(self, request, *args, **kwargs):
        self.get_object().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetRequestView(APIView):
    """
    POST /api/v1/auth/password-reset/ — {email}

    Always returns the same generic message whether or not the email exists, so this
    endpoint can't be used to check which emails have accounts (user enumeration).
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        user = User.objects.filter(email__iexact=email).first()
        if user is not None:
            code = PasswordResetCode.objects.create(user=user, code=PasswordResetCode.generate_code())
            send_mail(
                subject="Your JR Analytics password reset code",
                message=(
                    f"Your password reset code is: {code.code}\n\n"
                    f"This code expires in {settings.PASSWORD_RESET_TIMEOUT_MINUTES} minutes. "
                    "If you didn't request this, you can safely ignore this email."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )

        return Response({"detail": "If an account exists for that email, a reset code has been sent."})


class PasswordResetConfirmView(APIView):
    """POST /api/v1/auth/password-reset/confirm/ — {email, code, new_password}"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password has been reset. You can now sign in."})
