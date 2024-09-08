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
                'cols': 35,  # Set the number of columns
                'rows': 5    # Set the number of rows
            }
        )
    )