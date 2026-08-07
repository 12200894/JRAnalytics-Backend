"""
JR Analytics API routes.

    /admin/                          Django admin — full CRUD over every table
    /api/v1/auth/register/           create an account, returns a JWT pair
    /api/v1/auth/login/              obtain a JWT pair
    /api/v1/auth/refresh/            exchange a refresh token for a new access token
    /api/v1/auth/me/                 read / update the signed-in profile
    /api/v1/notes/                   health notes CRUD
    /api/v1/summaries/               past AI summaries
    /api/v1/summaries/generate/      generate a new summary via the LLM service
    /api/v1/llm/status/              is the LLM service reachable?
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.views import ProfileView, RegisterView
from notes.views import AISummaryViewSet, HealthNoteViewSet, llm_status

router = DefaultRouter()
router.register("notes", HealthNoteViewSet, basename="note")
router.register("summaries", AISummaryViewSet, basename="summary")

urlpatterns = [
    path("admin/", admin.site.urls),

    path("api/v1/auth/register/", RegisterView.as_view(), name="register"),
    path("api/v1/auth/login/", TokenObtainPairView.as_view(), name="login"),
    path("api/v1/auth/refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("api/v1/auth/me/", ProfileView.as_view(), name="profile"),

    path("api/v1/llm/status/", llm_status, name="llm-status"),
    path("api/v1/", include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
