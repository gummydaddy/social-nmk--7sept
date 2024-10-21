from django.urls import path
from . import views

urlpatterns = [
    path('only_coin_dashboard/', views.only_coin_dashboard, name='only_coin_dashboard'),
]
