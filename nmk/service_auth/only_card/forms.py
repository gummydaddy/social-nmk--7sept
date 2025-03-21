from django import forms
from django_countries.fields import CountryField
from allauth.account.forms import SignupForm
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from .models import Group, UserUpload, RegistrationForm, Card, KYC, CustomGroup, CustomGroupAdmin
from cryptography.fernet import Fernet
from django.core.exceptions import ValidationError
import mimetypes
from django.core.validators import RegexValidator




class CustomSignupForm(SignupForm):
    field_order = ['username', 'email', 'first_name', 'last_name']

    username = forms.CharField(
        max_length=20, 
        label='Choose Username', 
        validators=[RegexValidator(r'^[a-zA-Z0-9]+$', 'Only alphanumeric characters allowed.')],
        widget=forms.TextInput(attrs={'placeholder': 'Enter username'})
    )
    first_name = forms.CharField(
        max_length=30, 
        label='First Name', 
        widget=forms.TextInput(attrs={'placeholder': 'Enter first name'})
    )
    last_name = forms.CharField(
        max_length=30, 
        label='Last Name', 
        widget=forms.TextInput(attrs={'placeholder': 'Enter last name'})
    )
    email = forms.EmailField(
        max_length=200, 
        label='Email Address', 
        help_text='Required', 
        error_messages={'required': 'Email is required.'},
        widget=forms.EmailInput(attrs={'placeholder': 'Enter email'})
    )

    def save(self, request, commit=True):
        user = super(CustomSignupForm, self).save(request)
        user.username = self.cleaned_data['username']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.email = self.cleaned_data['email']

        if commit:
            user.save()

        return user



# class PasswordResetForm(forms.Form):
#     email = forms.EmailField(max_length=200, help_text='Required', label="Email")


class PasswordResetForm(forms.Form):
    username_or_email = forms.CharField(max_length=200, help_text='Required', label="Username or Email")


class UserUploadForm(forms.ModelForm):
    country = CountryField().formfield(label='Country of Origin')
    document_type = forms.ChoiceField(choices=[
        ('aadhar_card', 'Aadhar Card'),
        ('pan_card', 'PAN Card'),
        ('driving_license', 'Driving License'),
        ('voter_id', 'Voter ID'),
        ('passport', 'Passport'),
        ('others', 'Others')
    ])

    class Meta:
        model = UserUpload
        fields = ['file_name', 'file', 'document_type', 'country']
    
    def clean_file(self):
        file = self.cleaned_data.get('file')

        # Add the supported MIME types here
        valid_mime_types = [
            'image/jpeg', 
            'image/png', 
            'video/mp4',
            'video/mov',
            'video/quicktime',
            'video/mpeg',
            'application/pdf', 
            'text/plain',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # docx
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',        # xlsx
            'application/vnd.ms-excel',  # .xls (old Excel format)
            'application/vnd.openxmlformats-officedocument.presentationml.presentation', # pptx
            'application/xml',  # .xml files
            'text/xml',  # .xml alternative MIME type
            'application/zip',  # Sometimes .xlsx and other Office files are sent as zips
            'text/x-python',  # Python files
            'application/json'  # For JSON files
        ]
        
        # Guess the MIME type of the file
        mime_type, encoding = mimetypes.guess_type(file.name)
        
        # Validate the file type against supported MIME types
        if mime_type and mime_type.lower() not in [fmt.lower() for fmt in valid_mime_types]:
        # if mime_type not in valid_mime_types:
            raise ValidationError(f"Unsupported file type: {mime_type}. Supported types are: jpg, jpeg, png, mp4, mov, quicktime, mpeg, pdf, txt, docx, xlsx, xls, pptx, py, xml, json, zip.")
        
        # Additional validation for .zip (folders)
        if mime_type == 'application/zip':
            from zipfile import ZipFile
            import io

            try:
                # Ensure the uploaded file is a valid zip archive
                with ZipFile(io.BytesIO(file.read())) as zf:
                    if not zf.namelist():
                        raise ValidationError("The uploaded folder is empty.")
            except Exception:
                raise ValidationError("The uploaded folder is not a valid zip file.")
        
        return file

        

#document existance 
def check_object_existence(upload_id):
    try:
        upload = UserUpload.objects.get(id=upload_id)
        print("UserUpload object exists with ID:", upload_id, {'upload':upload})
    except UserUpload.DoesNotExist:
        print("UserUpload object does not exist with ID:", upload_id)

# delete uploaded document 
class DeleteUploadForm(forms.Form):
    upload_id = forms.IntegerField(widget=forms.HiddenInput(), required=False)



#user kyc 
class KYCForm(forms.ModelForm):
    class Meta:
        model = KYC
        fields = ['uploaded_image', 'phone_number']


class CardForm(forms.ModelForm):
    class Meta:
        model = Card
        fields = [ 'card_image']

    

#ServiceProviderRegistrationForm
class RegistrationFormForm(forms.ModelForm):
    subgroup = forms.ModelChoiceField(queryset=CustomGroup.objects.all())

    class Meta:
        model = RegistrationForm
        fields = ['criteria', 'legal_documents', 'gst_number', 'subgroup', 'association_name']
        labels = {
            "criteria": "Eligibility Criteria (Govt. Scheme/Rules)",
            "legal_documents":"Legal Documents (Aadhar/Pan/Bank Passbook etc.)",
            "association_name": "Association Name",

        }
        widgets={
            "gst_number":forms.TextInput(attrs={"placeholder":"Enter GST Number"}),
        }


#group28april
class GroupCreationForm(forms.ModelForm):
    class Meta:
        model = CustomGroup
        fields = ['name', 'description']

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.instance.user = kwargs.get('user')  # Set the user instance on form initialization


class SubgroupSignupForm(forms.ModelForm):
    association_name = forms.CharField(max_length=300)
    association_email = forms.EmailField()
    # legal_documents = forms.FileField()

    class Meta:
        model = CustomGroup
        fields = ['name', 'parent_group', 'association_name', 'association_email', 'legal_documents_Association', 'pending_approval']
        labels = {
            "legal_documents_Association":"Legal Documents (companies ppf data)"
        }
        widgets = {
            'parent_group': forms.Select(),
            'pending_approval': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)  # Extract the 'user' argument if provided
        super(SubgroupSignupForm, self).__init__(*args, **kwargs)

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            if self.user is not None:
                instance.admins.add(self.user)
                # Create a CustomGroupAdmin instance
                CustomGroupAdmin.objects.create(group=instance, user=self.user)
        return instance
    


#     class RegistrationFormForm(forms.ModelForm):
#     class Meta:
#         model = RegistrationForm
#         fields = ['association_name', 'gst_number', 'country_of_origin', 'legal_documents']
#         labels = {
#             "association_name": "Association Name",
#             "gst_number": "GST Number or Legal Registration Number",
#             "country_of_origin": "Country of Origin",
#             "legal_documents": "Legal Documents (Aadhar/PAN/ID Card)"
#         }
#         widgets = {
#             "gst_number": forms.TextInput(attrs={"placeholder": "Enter GST or Registration Number"}),
#             "country_of_origin": forms.TextInput(attrs={"placeholder": "Enter Country of Origin"}),
#         }

# class GroupCreationForm(forms.ModelForm):
#     class Meta:
#         model = CustomGroup
#         fields = ['name', 'description']

#     def __init__(self, *args, **kwargs):
#         self.user = kwargs.pop('user', None)  # Extract the 'user' argument if provided
#         super().__init__(*args, **kwargs)

#     def save(self, commit=True):
#         instance = super().save(commit=commit)
#         if commit and self.user:
#             instance.admins.add(self.user)
#             CustomGroupAdmin.objects.create(group=instance, user=self.user)
#         return instance
