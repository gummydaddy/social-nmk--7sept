from django.urls import path
from . import views 
from service_auth.only_card import views as only_card_views  # Import views from only_card
from service_auth.user_profile import views as user_profile_views

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

    #new helper
    #path('chat/<str:username>/', views.chat_page, name='chat_page'),

    #path("messages/<int:user_id>/", views.chat_page, name="chat_page"),

    #path("api/messages/<int:user_id>/", views.fetch_messages, name="fetch_messages"),

    path('user_messages_view/<str:username>/', views.user_messages_view, name='user_messages_view'),
    #path('api/messages/<str:username>/', views.user_messages_view, name='user_messages_view'),


    #path('messages/<str:username>/delete/', views.delete_messages_view, name='delete_messages'),

    path('delete_messages/<str:username>/', views.delete_messages_view, name='delete_messages_view'),

    path('api/messages/<str:username>/', views.get_messages_api, name='get_messages_api'),
    path('get_online_users/', views.get_online_users, name='get_online_users'),

    path("api/notifications/", views.get_notifications_api, name="get_notifications_api"),

    path("api/notifications/mark-read/", views.mark_notifications_read, name="mark_notifications_read"),

    path("api/notifications/clear/", views.clear_notifications_api, name="clear_notifications_api"),

    path('stranger-chat/', views.stranger_chat_view, name='stranger_chat_view'),
    #path('<str:username>/', user_profile_views.profile_detail, name='profile_detail'), #new for sitemap purpose to add the username of users to the sitemap
    #path('<str:username>/media/<int:media_id>/', user_profile_views.media_detail, name='media_detail'), #new for sitemap purpose to add the username of users to the sitemap


]
