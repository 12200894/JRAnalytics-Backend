"""Registration and profile serializers. Validation lives here, not in views."""

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

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
