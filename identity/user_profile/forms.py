from django import forms
from django_select2.forms import Select2MultipleWidget
from django.contrib.auth.models import User as AuthUser
from .models import Media, Profile
from notion.models import Comment
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


# class ProfileForm(forms.ModelForm):
#     class Meta:
#         model = Profile
#         fields = ['profile_picture', 'cover_photo', 'bio']

#         def clean_bio(self):
#             bio = self.cleaned_data.get('bio', '')
#             # Linkify the bio
#             bio = bleach.linkify(bio)



class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['profile_picture', 'cover_photo', 'bio']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bio'].validators.append(MaxLengthValidator(150, 'Bio cannot exceed 150 words.'))

    def clean_bio(self):
        bio = self.cleaned_data.get('bio', '')
        # Linkify the bio
        bio = bleach.linkify(bio)
        return bio


    def save(self, commit=True):
        profile = super().save(commit=False)
        if self.cleaned_data['profile_picture']:
            profile_picture = self.cleaned_data['profile_picture']
            image = Image.open(profile_picture)
            image = image.resize((150, 150), Image.ANTIALIAS)

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
