"""
Custom user model, keyed on email rather than username.

Django's default User requires a username. Health apps identify people by email,
and swapping this later means a painful migration, so it is done up front.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Django calls into this when creating users. Email replaces username."""

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Users must have an email address")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)          # hashes with PBKDF2-SHA256, never stores plaintext
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_active", True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=120, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    # notification preferences surfaced on the profile screen
    daily_reminder = models.BooleanField(default=True)
    weekly_summary_email = models.BooleanField(default=True)

    # captured at registration — Australian Privacy Principle 3 requires explicit consent
    privacy_consent_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)   # administrators toggle this to disable an account
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email
