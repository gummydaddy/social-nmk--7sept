# nmk_chain/urls.py

from django.urls import path
from . import views
from only_card import views as only_card_views  # Import views from only_card

app_name = 'nmk_chain'


urlpatterns = [
    path('index/', views.index, name='index'),
    path('transaction/', views.transaction, name='transaction'),
    path('buy/', views.buy, name='buy'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('accounts/login/', only_card_views.login_view, name='login'),  # Use the login view from only_card
    path('accounts/logout/', only_card_views.logout_view, name='logout'),  # Use the logout view from only_card
    path('accounts/signup/', only_card_views.signup, name='signup'),  # Use the signup view from only_card


]
