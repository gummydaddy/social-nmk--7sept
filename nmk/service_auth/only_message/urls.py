from django.urls import path
from . import views 
from service_auth.only_card import views as only_card_views  # Import views from only_card
from service_auth.user_profile import views as user_profile_views
from . import live_views
from . import group_views

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
    path('crumbing/', views.stranger_chat_view, name='stranger_chat_view'),

    # user dm counter setup
    path('api/messages/unread-counts/', views.dm_unread_counts_api, name='dm_unread_counts_api'),
    path('api/nav/unread-counts/', views.unread_counts_api, name='unread_counts_api'),

    #user audio and video calling setup
    path('call/<str:call_id>/', views.call_page_view, name='call_page'),
    path('api/call/<str:call_id>/pending/', views.get_pending_call_api, name='get_pending_call_api'),
    path('api/call/<str:call_id>/decline/', views.decline_call_api, name='decline_call_api'),

    #Live
    path('live/', live_views.live_list_view, name='live_list_view'),
    path('live/start/', live_views.start_live_view, name='start_live_view'),
    path('live/<str:room_id>/', live_views.live_room_view, name='live_room_view'),
    path('api/live/rooms/', live_views.live_rooms_api, name='live_rooms_api'),
    path('api/live/<str:room_id>/end/', live_views.end_live_room_api, name='end_live_room_api'),
    path('group/<str:group_id>/live/start/', live_views.start_group_live_view, name='group_start_live_view'),

    #group messaging
    path('groups/', group_views.group_list_view, name='group_list_view'),
    path('groups/create/', group_views.create_group_view, name='create_group_view'),
    path('groups/search/', group_views.search_channels_view, name='search_channels_view'),   # NEW

    path('group/<str:group_id>/', group_views.group_chat_view, name='group_chat_view'),
    path('group/<str:group_id>/leave/', group_views.leave_group_view, name='leave_group_view'),
    path('group/<str:group_id>/delete/', group_views.delete_group_view, name='delete_group_view'),
    path('group/<str:group_id>/mute/', group_views.mute_group_view, name='mute_group_view'),
    path('group/<str:group_id>/reset-invite/', group_views.reset_invite_view, name='reset_invite_view'),
    path('group/<str:group_id>/members/', group_views.group_members_api, name='group_members_api'),
    #path('invite/<str:code>/', group_views.join_via_invite_view, name='join_via_invite_view'),
    path('group/<str:group_id>/search-users/', group_views.search_addable_users_api, name='group_search_users_api'),  # NEW

    path('groups/unread-counts/', group_views.group_unread_counts_api, name='group_unread_counts_api'),

    path('group/<str:group_id>/upload/', group_views.group_file_upload_view, name='group_file_upload_view'),
    path('invite/<str:code>/', group_views.invite_landing_view, name='invite_landing_view'),   # CHANGED

    # Web Push
    path('api/push/subscribe/',   views.push_subscribe,        name='push_subscribe'),
    path('api/push/unsubscribe/', views.push_unsubscribe,      name='push_unsubscribe'),
    path('api/push/vapid-key/',   views.vapid_public_key_view, name='vapid_public_key'),
    path('api/push/test/',        views.test_push_notification,   name='test_push'),


    #path('<str:username>/', user_profile_views.profile_detail, name='profile_detail'), #new for sitemap purpose to add the username of users to the sitemap
    #path('<str:username>/media/<int:media_id>/', user_profile_views.media_detail, name='media_detail'), #new for sitemap purpose to add the username of users to the sitemap


]
