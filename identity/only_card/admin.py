from django.contrib import admin
from .models import UserUpload, RegistrationForm, File, Card, KYC, CustomGroup, CustomGroupAdmin, UserAssociation
from .forms import GroupCreationForm
from django.contrib import messages
from django.urls import reverse
from django.shortcuts import redirect



# Register your models here.
admin.site.register(UserUpload)  # Register Group model with the custom admin site
admin.site.register(RegistrationForm)  # Register Group model with the custom admin site
admin.site.register(File)  # Register Group model with the custom admin site
admin.site.register(Card)  # Register Group model with the custom admin site
admin.site.register(KYC)  # Register Group model with the custom admin site
admin.site.register(CustomGroupAdmin)  # Register Group model with the custom admin site


#29april
class CustomGroupAdminInline(admin.StackedInline):
    model = CustomGroupAdmin
    extra = 1

@admin.register(CustomGroup)
class CustomGroupAdmin(admin.ModelAdmin):
    form = GroupCreationForm
    inlines = [CustomGroupAdminInline]
    list_display = ('name', 'description', 'parent_group', 'pending_approval', 'legal_documents_Association', 'get_associated_users')
    list_filter = ('parent_group', 'pending_approval')
    search_fields = ('name', 'description')
    actions = ['approve_groups', 'deny_groups']

    def approve_groups(self, request, queryset):
        updated = queryset.update(pending_approval='approve', is_approved=True)
        self.message_user(request, f"{updated} group(s) approved successfully.", messages.SUCCESS)
        # Redirect to the group list page
        #return redirect(reverse('only_card:group_list'))

    def deny_groups(self, request, queryset):
        updated = queryset.update(pending_approval='deny')
        self.message_user(request, f"{updated} group(s) denied successfully.", messages.SUCCESS)
        # Redirect to the group list page
        #return redirect(reverse('only_card:group_list'))

    
    def get_associated_users(self, obj):
        registrations = RegistrationForm.objects.filter(subgroup=obj)
        return ", ".join(registration.user.username for registration in registrations)

    get_associated_users.short_description = 'Associated Users'




@admin.register(UserAssociation)
class UserAssociationAdmin(admin.ModelAdmin):
    list_display = ('user', 'subgroup', 'association_name', 'association_email', 'is_approved')
    list_filter = ('is_approved',)