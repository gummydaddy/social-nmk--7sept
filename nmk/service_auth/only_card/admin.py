from django.contrib import admin
from .models import UserUpload, RegistrationForm, File, Card, KYC, CustomGroup, CustomGroupAdmin, UserAssociation, UserStorage, TemporaryUser#, TemporarilyLock
from .forms import GroupCreationForm
from django.contrib import messages
from django.urls import reverse
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _




# Register your models here.
# admin.site.register(UserUpload)  # Register Group model with the custom admin site
admin.site.register(RegistrationForm)  # Register Group model with the custom admin site
admin.site.register(File)  # Register Group model with the custom admin site
admin.site.register(Card)  # Register Group model with the custom admin site
admin.site.register(KYC)  # Register Group model with the custom admin site
admin.site.register(CustomGroupAdmin)  # Register Group model with the custom admin site
admin.site.register(UserStorage)  # Register Group model with the custom admin site
admin.site.register(TemporaryUser)  # Register Group model with the custom admin site
# admin.site.register(TemporarilyLock)  # Register Group model with the custom admin site


class DocumentTypeFilter(admin.SimpleListFilter):
    title = "Document Type"
    parameter_name = "document_type"

    def lookups(self, request, model_admin):
        # Dynamically fetch distinct document types for filtering
        document_types = UserUpload.objects.values_list("document_type", flat=True).distinct()
        return [(doc_type, doc_type) for doc_type in document_types]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(userupload__document_type=self.value())
        return queryset

class UserUploadInline(admin.TabularInline):  # Display UserUpload in a tabular format
    model = UserUpload
    fields = ["document_type", "file_name", "upload_date", "country", "is_folder"]
    readonly_fields = ["upload_date"]
    extra = 0

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if hasattr(self, "parent_object"):
            return qs.filter(user_storage=self.parent_object)
        return qs.none()

    def get_parent_object(self, obj):
        self.parent_object = obj

# class UserStorageAdmin(admin.ModelAdmin):
#     list_display = ["user", "total_storage_used_in_mb"]
#     list_filter = ["user__is_active", DocumentTypeFilter]
#     search_fields = ["user__username"]
#     inlines = [UserUploadInline]

#     def total_storage_used_in_mb(self, obj):
#         # Convert bytes to MB for display
#         return f"{obj.total_storage_used / (1024 * 1024):.2f} MB"
#     total_storage_used_in_mb.short_description = "Total Storage Used (MB)"

#     def get_inline_instances(self, request, obj=None):
#         # Pass parent object to the inline for filtering uploads
#         inline_instances = super().get_inline_instances(request, obj)
#         for inline in inline_instances:
#             if isinstance(inline, UserUploadInline):
#                 inline.get_parent_object(obj)
#         return inline_instances


class UserUploadAdmin(admin.ModelAdmin):
    list_display = ["user", "document_type", "file_name", "upload_date", "country", "is_folder"]
    list_filter = ["document_type", "country", "is_folder", "upload_date"]
    search_fields = ["user__username", "file_name", "document_type"]
    readonly_fields = ["upload_date", "encryption_key"]

    def save_model(self, request, obj, form, change):
        # Automatically set the user for the upload if not already set
        if not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)

# admin.site.register(UserStorage, UserStorageAdmin)
admin.site.register(UserUpload, UserUploadAdmin)




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



# @admin.register(TemporarilyLock)
# class UserAdmin(admin.ModelAdmin):
#     # ...
#     actions = ['lock_user', 'unlock_user']

#     def lock_user(self, request, queryset):
#         for user in queryset:
#             lock_user(request, user.id)
#     lock_user.short_description = "Lock selected users"

#     def unlock_user(self, request, queryset):
#         for user in queryset:
#             unlock_user(request, user.id)
#     unlock_user.short_description = "Unlock selected users"



@admin.register(UserAssociation)
class UserAssociationAdmin(admin.ModelAdmin):
    list_display = ('user', 'subgroup', 'association_name', 'association_email', 'is_approved')
    list_filter = ('is_approved',)