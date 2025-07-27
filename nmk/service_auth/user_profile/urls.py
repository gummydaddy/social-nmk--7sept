from django.urls import path
from . import views, admin

from service_auth.only_card import views as only_card_views  # Import views from only_card
from service_auth.notion import views as notion_views  # Import views from only_card
from service_auth.only_message import views as only_message_views



app_name = 'user_profile'
#add <str:username>/ tp profile to display username in the navigation bar 
urlpatterns = [
    path('profile/<int:user_id>/', views.profile, name='profile'),
    
    path('profile/<int:user_id>/edit/', views.edit_profile, name='edit_profile'),
    path('save_bio/', views.save_bio, name='save_bio'),

    path('media/<int:media_id>/', views.media_detail_view, name='media_detail_view'),
    
    path('upload-audio/', views.upload_audio, name='upload_audio'),
    path('delete_audio/delete/<int:audio_id>/', views.delete_audio, name='delete_audio'),
    path('voices/<int:user_id>/', views.voices, name='voices'),  #
    path('like_audio/<int:audio_id>/', views.like_audio, name='like_audio'),
    path('comment_audio/<int:audio_id>/', views.comment_audio, name='comment_audio'),
    path('delete_user_audio_comment/<int:comment_id>/', views.delete_user_audio_comment, name='delete_user_audio_comment'),

    path('follow_user/<int:user_id>/', views.follow_user, name='follow_user'),
    path('unfollow_user/<int:user_id>/', views.unfollow_user, name='unfollow_user'),
    path('upload_media/', views.upload_media, name='upload_media'),
    # path('media/tags/', views.media_tags, name='media_tags'),  # New URL for tagged media
    path('media/tags/<int:user_id>/', views.media_tags, name='media_tags'),  # New URL for user's tagged media
    path('explore/', views.explore, name='explore'),

    path('log_interaction/', views.log_interaction, name='log_interaction'),


    path('search_uploads/', views.search_uploads, name='search_uploads'),
    path('explore_detail/<int:media_id>/', views.explore_detail, name='explore_detail'),
    path('following_media/', views.following_media, name='following_media'),

    path('following_list/<int:user_id>', notion_views.following_list, name='following_list'),
    path('followers_list/<int:user_id>', notion_views.followers_list, name='followers_list'),
    path('remove-follower/<int:user_id>/', views.remove_follower, name='remove_follower'),
    path('toggle_privacy/', views.toggle_privacy, name='toggle_privacy'),
    path('update_category/', views.update_category, name='update_category'),
    path('fetch_categories/', views.fetch_categories, name='fetch_categories'),
    path('media/<int:media_id>/toggle_privacy/', views.toggle_media_privacy, name='toggle_media_privacy'),
    path('password_reset/', only_card_views.password_reset, name='password_reset'),
    

    path('media_engagement/<int:media_id>/engagement/', views.media_engagement, name='media_engagement'),


    path('my_notions/', notion_views.my_notions, name='my_notions'),  # Add this line
    path('search_users/', views.search_users, name='search_users'),
    path('tag-user-search/', views.tag_user_search, name='tag_user_search'), #tag user search
    path('profile_notifications/', views.profile_notifications, name='profile_notifications'),
    path('delete_media/delete/<int:media_id>/', views.delete_media, name='delete_media'),
    path('like_media/<int:media_id>/', views.like_media, name='like_media'),
    path('comment_media/<int:media_id>/', views.comment_media, name='comment_media'),
    path('delete_user_comment/<int:comment_id>/', views.delete_user_comment, name='delete_user_comment'),

    path('not_interested/<int:media_id>/', views.not_interested, name='not_interested'),
    path('report_media/<int:media_id>/', views.report_media, name='report_media'),
    path('admin/review_reports/', admin.admin_review_reports, name='admin_review_reports'),
    path('admin/handle_report/<int:notification_id>/<str:action>/', admin.handle_report, name='handle_report'),

    path('send_message_view/', only_message_views.send_message_view, name='send_message_view'),

    path('save/<int:media_id>/', views.save_upload, name='save_upload'),
    path('saved/', views.saved_uploads, name='saved_uploads'),

    path('add_story/', views.add_story, name='add_story'),
    path('story/<int:story_id>/', views.view_story, name='view_story'),
    
    path('block-user/<int:user_id>/', notion_views.block_user, name='block_user'),
    path('unblock-user/<int:user_id>/', notion_views.unblock_user, name='unblock_user'),
    path('blocked-users/', notion_views.blocked_user_list, name='blocked_user_list'),

    path('buddy_list/', views.buddy_list, name='buddy_list'),
    path('add_to_buddy/<int:user_id>/', views.add_to_buddy, name='add_to_buddy'),
    path('remove_from_buddy_list/<int:user_id>/', views.remove_from_buddy_list, name='remove_from_buddy_list'),

    path('accounts/login/', only_card_views.login_view, name='login'),  # Use the login view from only_card
    path('accounts/logout/', only_card_views.logout_view, name='logout'),  # Use the logout view from only_card
    path('accounts/signup/', only_card_views.signup, name='signup'),  # Use the signup view from only_card



]
