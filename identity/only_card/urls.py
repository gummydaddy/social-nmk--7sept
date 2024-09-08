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
from . import views


app_name = "only_card"
# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path('', views.home, name="home"),
    # path('', views.login_view, name="home"),
    path("signup/", views.signup, name="signup"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path('landing_page/', views.landing_page, name='landing_page'),
    path('password_reset/', views.password_reset, name='password_reset'),
    path('upload/', views.upload_document, name='upload_document'),
    path('view_file/<int:upload_id>/', views.view_file, name='view_file'),
    path('delete_upload/<int:upload_id>/', views.delete_upload, name='delete_upload'),
    path('RegistrationForm/', views.registration_form_view, name='RegistrationForm'),
    path('super_user_landing_page/', views.super_user_landing_page, name='super_user_landing_page'),
    path('send-file/', views.send_file, name='send_file'),
    path('create_card/', views.create_card, name='create_card'),
    path('create-kyc/', views.create_kyc, name='create_kyc'),
    path('service1/', views.service1, name='service1'),
    path('service2/', views.service2, name='service2'),
    path('service3/', views.service3, name='service3'),
    path('group_list/', views.group_list, name='group_list'),
    # path('groupbase/', views.groupbase, name='groupbase'),
    path('groups/create/', views.group_create, name='group_create'),
    path('subgroups/', views.subgroup_signup, name='subgroup_signup'),
    path('subgroup_landing_page/', views.subgroup_landing_page, name='subgroup_landing_page'),

    
]



