from django.urls import path
from . import views 
from only_card import views as only_card_views  # Import views from only_card


app_name = 'only_message'

urlpatterns = [
    path('accounts/login/', only_card_views.login_view, name='login'),  # Use the login view from only_card
    path('accounts/logout/', only_card_views.logout_view, name='logout'),  # Use the logout view from only_card
    path('accounts/signup/', only_card_views.signup, name='signup'),  # Use the signup view from only_card
    # path('user_list/', views.user_list, name='user_list'),
    path('_base/', views._base, name='_base'),
    path('search_user_message/', views.search_user_message, name='search_user_message'),
    path('send_message_view/', views.send_message_view, name='send_message_view'),
    path('message_list_view/', views.message_list_view, name='message_list_view'),
    path('user_messages_view/<str:username>/', views.user_messages_view, name='user_messages_view'),
    path('api/messages/<str:username>/', views.get_messages_api, name='get_messages_api'),
    path('get_online_users/', views.get_online_users, name='get_online_users'),



]