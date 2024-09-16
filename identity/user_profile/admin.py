from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, get_object_or_404, redirect
from .models import Media, Profile, Engagement, AdminNotification, UserHashtagPreference, Story, Hashtag #,Comment
from notion.models import Follow, Comment
from django.urls import path



# Register your models here.
admin.site.register(Media)  # Register Group model with the custom admin site
# admin.site.register(Follow)  # Register Group model with the custom admin site
admin.site.register(Profile)  # Register Group model with the custom admin site
admin.site.register(Engagement)  # Register Group model with the custom admin site
admin.site.register(UserHashtagPreference)  # Register Group model with the custom admin site
admin.site.register(Story)  # Register Group model with the custom admin site
admin.site.register(Hashtag)  # Register Group model with the custom admin site



# @staff_member_required
# def admin_review_reports(request):
#     reports = AdminNotification.objects.filter(reviewed=False)
#     context = {'reports': reports}
#     return render(request, 'admin/review_reports.html', context)

# @staff_member_required
# def handle_report(request, notification_id, action):
#     notification = get_object_or_404(AdminNotification, id=notification_id)
#     media = notification.media

#     if action == 'remove':
#         media.file.delete(save=False)
#         media.delete()
#         messages.success(request, 'Media removed successfully.')
#     elif action == 'ignore':
#         messages.info(request, 'Report ignored.')

#     notification.reviewed = True
#     notification.save()

#     return redirect('admin_review_reports')


# Custom view to review reports (available at the admin site)
@staff_member_required
def admin_review_reports(request):
    reports = AdminNotification.objects.filter(reviewed=False)
    context = {'reports': reports}
    return render(request, 'admin/review_reports.html', context)

# Custom view to handle a report (remove/ignore)
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

# Custom URLs for the admin views
class CustomAdminSite(admin.AdminSite):
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('review-reports/', admin_review_reports, name='admin_review_reports'),
            path('handle-report/<int:notification_id>/<str:action>/', handle_report, name='handle_report'),
        ]
        return custom_urls + urls

# Register the model and integrate with custom views
@admin.register(AdminNotification)
class AdminNotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'reviewed', 'created_at')  # Customize based on your model fields
    actions = ['mark_as_reviewed']

    def mark_as_reviewed(self, request, queryset):
        queryset.update(reviewed=True)
        self.message_user(request, "Selected notifications marked as reviewed.")
    
    mark_as_reviewed.short_description = "Mark selected notifications as reviewed"

# In settings.py, replace the default admin site with this custom one:
# admin.site = CustomAdminSite(name='custom_admin')