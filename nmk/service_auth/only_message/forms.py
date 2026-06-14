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
            MAX_UPLOAD_SIZE = 10 * 1024 * 1024 # 5 MB
            if uploaded_file.size > MAX_UPLOAD_SIZE:
                raise ValidationError(f"File size cannot exceed {MAX_UPLOAD_SIZE / (1024 * 1024)} MB.")

            # Allowed file types (e.g., images, PDFs, common documents)
            allowed_mimetypes = [
                'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml',


                # Videos
                'video/mp4',
                'video/webm',
                'video/quicktime',      # .mov
                'video/x-msvideo',      # .avi
                'video/x-matroska',     # .mkv
                'video/mpeg',

                # Audio
                'audio/mpeg',           # .mp3
                'audio/wav',
                'audio/ogg',
                'audio/mp4',            # .m4a
                'audio/x-m4a',

                # PDF
                'application/pdf',

                # Word
                'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', # .doc, .docx

                # Excel
                'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', # .xls, .xlsx

                # Text
                'text/plain',
                'text/csv',



                # APK
                'application/vnd.android.package-archive',

                'application/vnd.ms-powerpoint', 'application/vnd.openxmlformats-officedocument.presentationml.presentation',   #ppt

                # Archives
                'application/zip',
                'application/x-zip-compressed',
                'application/x-rar-compressed',
                'application/x-7z-compressed',
                'application/gzip',

                # Code files
                'application/json',
                'application/xml',
                'text/html',
                'text/css',
                'text/javascript',
                'application/javascript',
                'text/x-python',

            ]
            if uploaded_file.content_type not in allowed_mimetypes:
                raise ValidationError("Unsupported file type.")
        return uploaded_file
