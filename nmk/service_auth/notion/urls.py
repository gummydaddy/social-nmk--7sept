from django.urls import path
from . import views
from service_auth.only_card import views as only_card_views  # Import views from only_card

app_name = "notion" 


urlpatterns = [
    # path('notion_home/', views.notion_home, name='notion_home'),
    path('notion_home/<int:notion_id>/', views.notion_home, name='notion_home'),
    path('explorer/', views.notion_explorer, name='notion_explorer'),
    path('following_list/<int:user_id>/', views.following_list, name='following_list'),
    path('followers_list/', views.followers_list, name='followers_list'),
    path('followers_list/<int:user_id>/', views.followers_list, name='followers_list'),
    path('post_notion/', views.post_notion, name='post_notion'),
    # path('follow_user/<int:user_id>/', views.follow_user, name='follow_user'),
    path('post_comment/<int:notion_id>/', views.post_comment, name='post_comment'),
    path('delete_comment/<int:comment_id>/', views.delete_comment, name='delete_comment'),
    path('like_notion/<int:notion_id>/', views.like_notion, name='like_notion'),
    path('search_users/', views.search_users, name='search_users'),
    # path('my_notions/', views.my_notions, name='my_notions'),
    path('my_notions/<int:notion_id>/', views.my_notions, name='my_notions'),
    path('notion/<int:notion_id>/', views.notion_detail_view, name='notion_detail'),
    path('notifications/', views.notifications, name='notifications'),
    path('accounts/login/', only_card_views.login_view, name='login'),
    path('accounts/logout/', only_card_views.logout_view, name='logout'),
    path('accounts/signup/', only_card_views.signup, name='signup'),

    path('block-user/<int:user_id>/', views.block_user, name='block_user'),
    path('unblock-user/<int:user_id>/', views.unblock_user, name='unblock_user'),
    path('blocked-users/', views.blocked_user_list, name='blocked_user_list'),
    path('notion/<int:notion_id>/delete/', views.delete_notion, name='delete_notion'),

]
