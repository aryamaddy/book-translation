from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from django.urls import re_path
from django.views.static import serve

from reader.views import safe_google_login

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/google/login/', safe_google_login, name='google_login'),
    path('accounts/', include('allauth.urls')),
    path('', include('reader.urls')),
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': str(settings.MEDIA_ROOT)}),
]
