from django.urls import include, path
from django.contrib import admin

urlpatterns = [
    path('review/', include('review.urls')),
    path('admin/', admin.site.urls),
]