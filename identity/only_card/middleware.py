# middleware.py
from django.shortcuts import redirect
from django.urls import reverse
from .models import CustomGroup

class SubgroupApprovalMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            approved_subgroups = CustomGroup.objects.filter(users=request.user, is_approved=True)
            if approved_subgroups.exists():
                return redirect(reverse('only_card:subgroup_landing_page'))

        response = self.get_response(request)
        return response