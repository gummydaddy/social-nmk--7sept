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

    file = forms.FileField(required=False)  # New file field for optional file upload

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if uploaded_file:
            # Max file size (e.g., 5MB)
            MAX_UPLOAD_SIZE = 5 * 1024 * 1024 # 5 MB
            if uploaded_file.size > MAX_UPLOAD_SIZE:
                raise ValidationError(f"File size cannot exceed {MAX_UPLOAD_SIZE / (1024 * 1024)} MB.")

            # Allowed file types (e.g., images, PDFs, common documents)
            allowed_mimetypes = [
                'image/jpeg', 'image/png', 'image/gif',
                'application/pdf',
                'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', # .doc, .docx
                'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', # .xls, .xlsx
                'text/plain'
            ]
            if uploaded_file.content_type not in allowed_mimetypes:
                raise ValidationError("Unsupported file type.")
        return uploaded_file
