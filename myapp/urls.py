import os
from django.urls import path, re_path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    # path('', views.home, name='home'),  # This line matches the root URL
    # path('', views.index, name='index'),
    # path('<path:path>', views.index, name='index'),  # Catch-all pattern to handle client-side routing
    # path('sync/', views.start_sync, name='start_sync'),
    # path('logs/', views.get_logs, name='get_logs'),
    path('', views.index, name='index'),
    re_path(r'^.*$', views.index, name='index'),  # This will handle all paths

]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=os.path.join(settings.BASE_DIR, 'dist', 'assets'))