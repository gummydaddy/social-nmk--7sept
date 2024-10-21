# middleware.py
from django.utils.timezone import now
from .models import LoggedInUser

class UpdateLastActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            # Update last activity time
            request.user.logged_in_user, created = LoggedInUser.objects.get_or_create(user=request.user)
            request.user.logged_in_user.last_activity = now()
            request.user.logged_in_user.save()
        return response



# from django.utils.timezone import now
# from .models import LoggedInUser

# class UpdateLastActivityMiddleware:
#     def __init__(self, get_response):
#         self.get_response = get_response

#     def __call__(self, request):
#         response = self.get_response(request)
#         if request.user.is_authenticated:
#             # Update last activity time
#             LoggedInUser.objects.update_or_create(
#                 user=request.user,
#                 defaults={'last_activity': now()}
#             )
#         return response