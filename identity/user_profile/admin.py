from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, get_object_or_404, redirect
from .models import Media, Profile, Engagement, AdminNotification, UserHashtagPreference, Story, Hashtag #,Comment
from notion.models import Follow, Comment


# Register your models here.
admin.site.register(Media)  # Register Group model with the custom admin site
# admin.site.register(Follow)  # Register Group model with the custom admin site
admin.site.register(Profile)  # Register Group model with the custom admin site
admin.site.register(Engagement)  # Register Group model with the custom admin site
admin.site.register(UserHashtagPreference)  # Register Group model with the custom admin site
admin.site.register(Story)  # Register Group model with the custom admin site
admin.site.register(Hashtag)  # Register Group model with the custom admin site



@staff_member_required
def admin_review_reports(request):
    reports = AdminNotification.objects.filter(reviewed=False)
    context = {'reports': reports}
    return render(request, 'admin/review_reports.html', context)

@staff_member_required
def handle_report(request, notification_id, action):
    notification = get_object_or_404(AdminNotification, id=notification_id)
    media = notification.media

    if action == 'remove':
        media.file.delete(save=False)
        media.delete()
        messages.success(request, 'Media removed successfully.')
    elif action == 'ignore':
        messages.info(request, 'Report ignored.')

    notification.reviewed = True
    notification.save()

    return redirect('admin_review_reports')
