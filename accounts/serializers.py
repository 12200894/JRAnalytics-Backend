"""Registration and profile serializers. Validation lives here, not in views."""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers

from .models import PasswordResetCode

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    privacy_consent = serializers.BooleanField(write_only=True)

    class Meta:
        model = User
        fields = ("email", "full_name", "password", "password_confirm", "privacy_consent")

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate_password(self, value):
        if not any(c.isdigit() for c in value):
            raise serializers.ValidationError("Password must contain at least one number.")
        return value

    def validate(self, data):
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        if not data["privacy_consent"]:
            raise serializers.ValidationError(
                {"privacy_consent": "You must consent to the privacy terms to register."})
        return data

    def create(self, validated):
        validated.pop("password_confirm")
        validated.pop("privacy_consent")
        password = validated.pop("password")
        user = User.objects.create_user(password=password, **validated)
        user.privacy_consent_at = timezone.now()   # APP 3 — record when consent was given
        user.save(update_fields=["privacy_consent_at"])
        return user


class UserSerializer(serializers.ModelSerializer):
    note_count = serializers.IntegerField(source="notes.count", read_only=True)

    class Meta:
        model = User
        fields = ("id", "email", "full_name", "date_of_birth", "daily_reminder",
                  "weekly_summary_email", "date_joined", "note_count")
        read_only_fields = ("id", "email", "date_joined", "note_count")


class ChangePasswordSerializer(serializers.Serializer):
    """Requires the current password so a stolen/left-open session can't silently take over the account."""

    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        # Runs the same AUTH_PASSWORD_VALIDATORS used at registration (length, common
        # passwords, all-numeric, similarity to user attributes).
        validate_password(value, user=self.context["request"].user)
        return value

    def save(self):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Intentionally never reveals whether the email exists — the view always returns the
    same generic success message. Only the internal is_valid() checks below determine
    whether an email actually goes out.
    """

    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6, min_length=6)
    new_password = serializers.CharField(write_only=True)

    def validate(self, data):
        try:
            user = User.objects.get(email__iexact=data["email"])
        except User.DoesNotExist:
            raise serializers.ValidationError({"code": "Invalid or expired code."})

        reset_code = (
            PasswordResetCode.objects.filter(user=user, code=data["code"]).order_by("-created_at").first()
        )
        if reset_code is None or not reset_code.is_valid():
            raise serializers.ValidationError({"code": "Invalid or expired code."})

        validate_password(data["new_password"], user=user)

        data["user"] = user
        data["reset_code"] = reset_code
        return data

    def save(self):
        user = self.validated_data["user"]
        reset_code = self.validated_data["reset_code"]
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        reset_code.used = True
        reset_code.save(update_fields=["used"])
        return user
