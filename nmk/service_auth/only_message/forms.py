from django import forms
from django.contrib.auth.models import User

# class MessageForm(forms.Form):
#     recipient = forms.CharField(max_length=150, widget=forms.HiddenInput())
#     content = forms.CharField(widget=forms.Textarea(attrs={'v-model': 'newMessage'}))    



class MessageForm(forms.Form):
    recipient = forms.CharField(max_length=150, widget=forms.HiddenInput())
    content = forms.CharField(
        widget=forms.Textarea(
            attrs={
                'v-model': 'newMessage',  # Vue.js model binding
                'cols': 35,
                'rows': 5
            }
        )
    )
    # file = forms.FileField(required=False)  # New file field for optional file upload