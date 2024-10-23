from django import forms
from django_select2.forms import Select2MultipleWidget
from django.contrib.auth.models import User as AuthUser

from .utils import linkify, make_usernames_clickable
from .models import Media, Profile, Audio, UserHashtagPreference, Hashtag
from service_auth.notion.models import Comment
from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import SimpleUploadedFile
import bleach
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator



class MediaForm(forms.ModelForm):
    start_time = forms.FloatField(required=False, widget=forms.HiddenInput())
    duration = forms.FloatField(required=False, widget=forms.HiddenInput())
    tags = forms.ModelMultipleChoiceField(
        queryset=AuthUser.objects.all(),
        widget=Select2MultipleWidget(
            attrs={'data-placeholder': 'Search for users to tag...', 'class': 'form-control'}
        ),
        required=False,
        label="Tag Users"
    )

    class Meta:
        model = Media
        fields = ['file', 'description', 'start_time', 'duration', 'tags'   ]
        


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']


class AudioForm(forms.ModelForm):
    tags = forms.ModelMultipleChoiceField(
        queryset=AuthUser.objects.all(),
        widget=Select2MultipleWidget(
            attrs={'data-placeholder': 'Search for users to tag...', 'class': 'form-control'}
        ),
        required=False
    )
    hashtags = forms.ModelMultipleChoiceField(
        queryset=UserHashtagPreference.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    class Meta:
        model = Audio
        fields = ('file', 'description', 'is_paid', 'is_private', 'duration')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5, 'cols': 50}),
        }
        # You can mark duration as required=False here as well.
        extra_kwargs = {
            'duration': {'required': False}
        }

    def clean_file(self):
        file = self.cleaned_data['file']
        allowed_types = ['audio/mpeg', 'audio/wav', 'audio/ogg']
        if file.content_type not in allowed_types:
            raise ValidationError('Unsupported file type. Only MP3, WAV, and OGG are allowed.')
        return file

    def clean_size(self):
        file = self.cleaned_data['file']
        if file.size > 100 * 1024 * 1024:  # 100 MB
            raise ValidationError('File size exceeds the maximum limit of 100MB.')
        return file.size

    def clean_duration(self):
        # Make sure to check if duration is available (optional)
        duration = self.cleaned_data.get('duration')
        if duration and (duration < 1 or duration > 3600):
            raise ValidationError('Duration must be between 1 second and 1 hour.')
        return duration



# class ProfileForm(forms.ModelForm):
#     class Meta:
#         model = Profile
#         fields = ['profile_picture', 'cover_photo', 'bio']

#         def clean_bio(self):
#             bio = self.cleaned_data.get('bio', '')
#             # Linkify the bio
#             bio = bleach.linkify(bio)



class ProfileForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bio'].validators.append(MaxLengthValidator(150, 'Bio cannot exceed 150 words.'))

    # def clean_bio(self):
    #     bio = self.cleaned_data.get('bio', '')
    #     # Linkify the bio
    #     bio = bleach.linkify(bio)
    #     return bio

    def clean_bio(self):
        bio = self.cleaned_data.get('bio', '')

        # # Linkify URLs first
        # bio = linkify(bio)
    
        # Then, make usernames clickable
        bio = make_usernames_clickable(bio)
    
        # Return the final processed bio
        return bio
    class Meta:
        model = Profile
        fields = ['profile_picture', 'cover_photo', 'bio']



    def save(self, commit=True):
        profile = super().save(commit=False)
        if self.cleaned_data['profile_picture']:
            profile_picture = self.cleaned_data['profile_picture']
            image = Image.open(profile_picture)
            # image = image.resize((150, 150), Image.ANTIALIAS)
            image = image.resize((150, 150), Image.LANCZOS)


            # Save the image to a BytesIO object
            image_io = BytesIO()
            image.save(image_io, format='JPEG')
            
            # Create a new SimpleUploadedFile object with the resized image
            profile.profile_picture = SimpleUploadedFile(profile_picture.name, image_io.getvalue(), content_type='image/jpeg')
        
        if commit:
            profile.save()
        return profile
    

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

    def value_from_datadict(self, data, files, name):
        if self.allow_multiple_selected:
            return files.getlist(name)
        return super().value_from_datadict(data, files, name)
        


class MultiMediaForm(forms.Form):
    files = forms.FileField(widget=MultipleFileInput(attrs={'multiple': True}), required=True)
    filter = forms.ChoiceField(choices=[
        ('', 'Select a filter'),
        ('clarendon', 'Clarendon'),
        ('sepia', 'Sepia'),
        ('grayscale', 'Grayscale'),
        ('invert', 'Invert')
    ], required=False)
    description = forms.CharField(widget=forms.Textarea, required=False)
    video_parts = forms.CharField(widget=forms.HiddenInput, required=False)  # Hidden input to hold selected parts
