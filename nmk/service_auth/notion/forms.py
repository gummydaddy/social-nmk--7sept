from django import forms
from django.contrib.auth.models import User as AuthUser
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator


class UsernameUpdateForm(forms.Form):
    new_username = forms.CharField(
        max_length=20, 
        label='New Username',

        validators=[RegexValidator(
            r'^[A-Za-z0-9._-]+$',
            'Username may only contain letters, numbers, underscores (_), hyphens (-), and dots (.)'
        )],

        #validators=[RegexValidator(r'^[a-zA-Z0-9]+$', 'Only alphanumeric characters allowed.')],
        widget=forms.TextInput(attrs={'placeholder': 'Enter new username'})  # This creates the input field
    )

    def clean_new_username(self):
        new_username = self.cleaned_data['new_username']
        if AuthUser.objects.filter(username=new_username).exists():
            raise ValidationError("This username is already taken.")
        return new_username
