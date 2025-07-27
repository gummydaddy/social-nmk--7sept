"""
URL configuration for nmk project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include 
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from django.contrib.sitemaps.views import sitemap
from service_auth.user_profile.sitemaps import StaticViewSitemap, ProfileSitemap, MediaSitemap
from service_auth.notion.sitemaps import NotionSitemap


#new sitemap
sitemaps = {
    'static': StaticViewSitemap(),
    'profiles': ProfileSitemap(),
    'media': MediaSitemap(),
    'notions': NotionSitemap(),
}

urlpatterns = [
   
    path("admin/", admin.site.urls),
   # path('accounts/', include('allauth.urls')),

    #app
    path('' , include('service_auth.only_card.urls')),
    # path('' , include('only_coin.urls')),
    path('' , include('service_auth.notion.urls', namespace='notion')),
    path('' , include('service_auth.user_profile.urls')),
    # path('' , include('nmk.nmk_chain.urls')),
    path('' , include('service_auth.only_message.urls', namespace='only_message')),
    
    path('accounts/login_view/', auth_views.LoginView.as_view(), name='login_view'),  # Login view

    path('accounts/', include('django.contrib.auth.urls')),

    path("api/auth/", include("rest_framework.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),

    #path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'), #new sitemap
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='sitemap'),
    path('robots.txt', TemplateView.as_view(template_name="robots.txt", content_type="text/plain")),


]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
#if settings.DEBUG:
    #urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


