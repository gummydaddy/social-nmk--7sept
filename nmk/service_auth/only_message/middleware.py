# middleware.py
from django.utils.timezone import now
from .models import LoggedInUser

"""
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
"""

'''
class UpdateLastActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            try:
                obj, created = LoggedInUser.objects.get_or_create(user=request.user)
                obj.last_activity = now()
                obj.save(update_fields=["last_activity"])
            except Exception:
                pass
        return response
'''


class UpdateLastActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.user.is_authenticated:
            LoggedInUser.objects.update_or_create(
                user=request.user,
                defaults={'last_activity': now()}
            )
        return response




class ServiceWorkerScopeMiddleware:
    """
    Adds  Service-Worker-Allowed: /  to the HTTP response for service-worker.js.
 
    Without this header the browser refuses to register a SW at
    /static/service-worker.js with scope '/' because the scope does not start
    with the script URL path (/static/).
 
    Works with:
      • Django dev server  (DEBUG=True, runserver)
      • WhiteNoise         (add BEFORE WhiteNoiseMiddleware in MIDDLEWARE list)
 
    For Nginx serving static files directly (bypasses Django):
      See the nginx.conf snippet at the bottom of this file instead.
    """
 
    def __init__(self, get_response):
        self.get_response = get_response
 
    def __call__(self, request):
        response = self.get_response(request)
 
        if 'service-worker.js' in request.path:
            response['Service-Worker-Allowed'] = '/'
            response['Cache-Control']          = 'no-cache, no-store, must-revalidate'
            response['Pragma']                 = 'no-cache'
 
        return response
