import pyrebase
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User  # Import the User model at the top
from django.http import HttpResponse, StreamingHttpResponse, HttpResponseNotFound, HttpResponseServerError
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.core.mail import send_mail, EmailMessage, get_connection
from django.core.cache import cache
from django.conf import settings
from .models import KYC, File, UserAssociation, UserUpload, RegistrationForm, CustomGroup, CustomGroupAdmin
from .forms import CustomSignupForm, UserUploadForm, DeleteUploadForm, RegistrationFormForm, KYCForm, CardForm, GroupCreationForm, SubgroupSignupForm
from twilio.rest import Client
from cryptography.fernet import Fernet
import os
import logging

firebaseConfig={
    'apiKey': "AIzaSyCN7s6q2iX84wAa-bcADtojDbRKRsK5UTk",
    'authDomain': "authporp.firebaseapp.com",
    'projectId': "authporp",
    'storageBucket': "authporp.appspot.com",
    'messagingSenderId': "746007263598",
    'appId': "1:746007263598:web:1d9cbb363e41cba3d3e97f",
    'measurementId': "G-MQ4Q1F4FCE",
    "databaseURL": "",  # Ensure this is included
}

firebase= pyrebase.initialize_app(firebaseConfig)
auth=firebase.auth()


def home(request):
    return render(request, 'home.html')


def send_confirmation_email(user):
    subject = "Welcome to NMK Financial Services - Django Login!"
    message = f"Hello {user.first_name},\nWelcome to NMK!\nThank you for being a part of our community."
    email_from = settings.EMAIL_HOST_USER
    recipient_list = [user.email]
    send_mail(subject, message, email_from, recipient_list)


# def signup(request):
#     if request.method == 'POST':
#         form = CustomSignupForm(request.POST)
#         if form.is_valid():
#             user = form.save(request)
#             # send_confirmation_email(user)
#             login(request, user)
#             messages.success(request, "Your account has been created successfully. Please check your email to confirm your account.")
#             return redirect('/')
#         else:
#             messages.error(request, "Failed to create account. Please check the form entries.")
#     else:
#         form = CustomSignupForm()
#     return render(request, 'signup.html', {'form': form})


def signup(request):
    if request.method == 'POST':
        form = CustomSignupForm(request.POST)
        if form.is_valid():
            # Extract user data from the form
            username = form.cleaned_data.get('username')
            email = form.cleaned_data.get('email')
            password = form.cleaned_data.get('password1')  # Assuming you have a password1 field
            first_name = form.cleaned_data.get('first_name')
            last_name = form.cleaned_data.get('last_name')

            try:
                # Create user with Firebase
                firebase_user = auth.create_user_with_email_and_password(email, password)
                # Send email verification
                auth.send_email_verification(firebase_user['idToken'])

                # Save user details in Django model without committing to the database
                user_model = form.save(request, commit=False)  # Pass request to save method
                user_model.first_name = first_name
                user_model.last_name = last_name
                user_model.email = email
                user_model.username = username  # Set username to username 
                user_model.save()  # Now commit to the database

                # Log the user in Django
                login(request, user_model)
                messages.success(request, "Your account has been created successfully. Please check your email to confirm your account.")
                return redirect('/')
            except Exception as e:
                # Handle Firebase authentication errors
                messages.error(request, f"Failed to create account: {e}")
        else:
            messages.error(request, "Failed to create account. Please check the form entries.")
    else:
        form = CustomSignupForm()
    return render(request, 'signup.html', {'form': form})

# Login
# def login_view(request):
#     if request.method == 'POST':
#         username_or_association = request.POST['username']
#         password = request.POST['pass1']
#         user = authenticate(request, username=username_or_association, password=password)
#         if user is not None:
#             login(request, user)
#             response = HttpResponse("You're logged in.")
#             response.set_cookie('username', username_or_association)
#             cache.set(f'user_{user.id}', user.username)
#             if CustomGroupAdmin.objects.filter(user=user).exists():
#                 return redirect('/subgroup_landing_page')
#             elif user.is_staff:
#                 return redirect('/super_user_landing_page')
#             else:
#                 return redirect('/landing_page')

#         try:
#             group = CustomGroup.objects.get(name=username_or_association)
#             user = group.users.first()
#             if user:
#                 login(request, user)
#                 request.session['association_name'] = username_or_association
#                 request.session['user_id'] = user.id
#                 cache.set(f'user_{user.id}', username_or_association)
#         except CustomGroup.DoesNotExist:
#             pass
#         messages.error(request, 'Invalid username or password')
#         return render(request, 'login_view.html')
#     else:
#         return render(request, 'login_view.html')


# def login_view(request):
#     if request.method == 'POST':
#         username_or_email = request.POST['username']
#         password = request.POST['pass1']

#         try:
#             # Validate email format if username_or_email is intended to be an email
#             if '@' not in username_or_email or '.' not in username_or_email:
#                 raise ValueError("Invalid email format")

#             # Firebase authentication
#             firebase_user = auth.sign_in_with_email_and_password(username_or_email, password)
#             user = authenticate(request, username=username_or_email, password=password)
            
#             if user is not None:
#                 # Log in the user in Django
#                 login(request, user)
#                 response = HttpResponse("You're logged in.")
#                 response.set_cookie('username', username_or_email)
#                 cache.set(f'user_{user.id}', user.username)
                
#                 if CustomGroupAdmin.objects.filter(user=user).exists():
#                     return redirect('/subgroup_landing_page')
#                 elif user.is_staff:
#                     return redirect('/super_user_landing_page')
#                 else:
#                     return redirect('/landing_page')

#             else:
#                 messages.error(request, 'Invalid username or password')

#         except ValueError as ve:
#             messages.error(request, str(ve))

#         except Exception as e:
#             # Handle Firebase authentication errors more gracefully
#             error_message = str(e)
#             if "INVALID_EMAIL" in error_message:
#                 messages.error(request, "The email address is invalid. Please check and try again.")
#             elif "INVALID_PASSWORD" in error_message:
#                 messages.error(request, "The password is incorrect. Please try again.")
#             else:
#                 messages.error(request, f"Failed to log in: {error_message}")

#         # Check if username is a group name for alternative authentication
#         try:
#             group = CustomGroup.objects.get(name=username_or_email)
#             user = group.users.first()
#             if user:
#                 login(request, user)
#                 request.session['association_name'] = username_or_email
#                 request.session['user_id'] = user.id
#                 cache.set(f'user_{user.id}', username_or_email)
#                 return redirect('/landing_page')
#         except CustomGroup.DoesNotExist:
#             pass

#         return render(request, 'login_view.html')

#     else:
#         return render(request, 'login_view.html')


def login_view(request):
    if request.method == 'POST':
        username_or_email = request.POST['username']
        password = request.POST['pass1']

        try:
            # Check if username_or_email is an email
            if '@' in username_or_email:
                # Try to authenticate with email
                user = User.objects.get(email=username_or_email)
                username = user.username
            else:
                # Try to authenticate with username
                username = username_or_email
                user = User.objects.get(username=username)

            # Firebase authentication
            firebase_user = auth.sign_in_with_email_and_password(user.email, password)

            # Authenticate and log in the user in Django
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                response = HttpResponse("You're logged in.")
                response.set_cookie('username', username)
                cache.set(f'user_{user.id}', user.username)

                if CustomGroupAdmin.objects.filter(user=user).exists():
                    return redirect('/subgroup_landing_page')
                elif user.is_staff:
                    return redirect('/super_user_landing_page')
                else:
                    return redirect('/landing_page')

            else:
                messages.error(request, 'Invalid username or password')

        except User.DoesNotExist:
            messages.error(request, 'Invalid username or email')

        except Exception as e:
            # Handle Firebase authentication errors more gracefully
            error_message = str(e)
            if "INVALID_EMAIL" in error_message:
                messages.error(request, "The email address is invalid. Please check and try again.")
            elif "INVALID_PASSWORD" in error_message:
                messages.error(request, "The password is incorrect. Please try again.")
            else:
                messages.error(request, f"Failed to log in: {error_message}")

        # Check if username is a group name for alternative authentication
        try:
            group = CustomGroup.objects.get(name=username_or_email)
            user = group.users.first()
            if user:
                login(request, user)
                request.session['association_name'] = username_or_email
                request.session['user_id'] = user.id
                cache.set(f'user_{user.id}', username_or_email)
                return redirect('/landing_page')
        except CustomGroup.DoesNotExist:
            pass

        return render(request, 'login_view.html')

    else:
        return render(request, 'login_view.html')
    

@staff_member_required
def super_user_landing_page(request):
    registration_forms = RegistrationForm.objects.all()
    return render(request, 'super_user_landing_page.html', {'registration_forms': registration_forms})

@login_required
def subgroup_landing_page(request):
    user_admin_groups = request.user.admin_groups.filter(is_approved=True)
    approved_groups = CustomGroup.objects.filter(is_approved=True)
    pending_requests = RegistrationForm.objects.filter(status='pending')
    context = {
        'user_admin_groups': user_admin_groups,
        'approved_groups': approved_groups,
        'pending_requests': pending_requests,
    }
    return render(request, 'subgroup_landing_page.html', context)


# LogOut
@login_required
def logout_view(request):
    user = request.user
    if user.is_authenticated:
        cache.delete(f'user_{user.id}')
    logout(request)
    request.session.flush()
    return redirect('/')


# Landing
@login_required   
def landing_page(request):
    user_username = cache.get(f'user_{request.user.id}')
    if not user_username:
        user_username = request.user.username
        cache.set(f'user_{request.user.id}', user_username, timeout=3600)
    try:
        user_card = request.user.card
    except User.card.RelatedObjectDoesNotExist:
        user_card = None
    user_uploads = UserUpload.objects.filter(user=request.user).order_by('-upload_date')[:]
    super_user = request.session.get('super_user', False)
    context = {
        'user_username': user_username,
        'user_uploads': user_uploads,
        'super_user': super_user,
        'user_card': user_card,
        'user_id': request.user.id,
    }
    return render(request, 'landing_page.html', context)

@login_required
def group_list(request):
    groups = CustomGroup.objects.all()
    return render(request, 'group_list.html', {'groups': groups})

@login_required
def group_create(request):
    if request.method == 'POST':
        form = GroupCreationForm(request.POST)
        if form.is_valid():
            group = form.save()
            return redirect('/group_list',{'group':group})
    else:
        form = GroupCreationForm()
    return render(request, 'customgroup_form.html', {'form': form})

@login_required
def subgroup_signup(request):
    if request.method == 'POST':
        form = SubgroupSignupForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your subgroup signup request has been submitted for approval.')
            return redirect('only_card:landing_page')
    else:
        form = SubgroupSignupForm(user=request.user)
    return render(request, 'subgroup_signup_form.html', {'form': form})


@login_required
def upload_document(request):
    if request.method == 'POST':
        form = UserUploadForm(request.POST, request.FILES)
        if form.is_valid():
            form.instance.user = request.user
            form.save()
            if CustomGroupAdmin.objects.filter(user=request.user).exists():
                return redirect('/subgroup_landing_page')
            else:
                return redirect('/landing_page')
    else:
        form = UserUploadForm()
    return render(request, 'upload_document.html', {'form': form})


# Set up logging
logger = logging.getLogger(__name__)

@login_required
def view_file(request, upload_id):
    try:
        upload = get_object_or_404(UserUpload, id=upload_id, user=request.user)

        if not upload.encryption_key:
            logger.error(f"Encryption key not found for file with ID {upload_id}")
            return HttpResponseServerError("Encryption key not found for this file.")

        try:
            fernet = Fernet(upload.encryption_key.encode('utf-8'))
        except Exception as e:
            logger.error(f"Error initializing Fernet cipher: {e}")
            return HttpResponseServerError("Failed to initialize decryption.")

        file_path = upload.file.path
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return HttpResponseNotFound("File not found")

        try:
            with open(file_path, 'rb') as encrypted_file:
                encrypted_file_data = encrypted_file.read()

            decrypted_file_data = fernet.decrypt(encrypted_file_data)

            response = StreamingHttpResponse(
                iter([decrypted_file_data]), 
                content_type='application/octet-stream'
            )
            response['Content-Disposition'] = f'attachment; filename="{upload.file_name}"'
            return response

        except Exception as e:
            logger.error(f"Error during file decryption: {e}")
            return HttpResponseServerError("Error decrypting file.")

    except Exception as e:
        logger.error(f"Unhandled exception in view_file: {e}")
        return HttpResponseServerError("An error occurred while processing your request.")
    

@login_required
def delete_upload(request, upload_id):
    upload = get_object_or_404(UserUpload, id=upload_id)
    if request.method == 'POST':
        form = DeleteUploadForm(request.POST)
        if form.is_valid():
            upload.delete_file()  # Ensure the file is deleted from the filesystem
            upload.delete()  # Delete the database record
            return redirect('/landing_page')
    else:
        form = DeleteUploadForm(initial={'upload_id': upload_id})
    return render(request, 'delete_upload.html', {'form': form})


def upload_file(request):
    if request.method == 'POST':
        uploaded_file = request.FILES['file']
        upload = UserUpload.objects.create(file=uploaded_file)
        return redirect('/upload_success')
    return render(request, 'upload_form.html',{'upload':upload})

def registration_form_view(request):
    if request.method == 'POST':
        form = RegistrationFormForm(request.POST, request.FILES)
        if form.is_valid():
            form.instance.user = request.user
            registration = form.save()
            subgroup_id = request.POST.get('subgroup')
            if subgroup_id:
                try:
                    subgroup = CustomGroup.objects.get(pk=subgroup_id)
                    registration.subgroup = subgroup
                    registration.save()
                except CustomGroup.DoesNotExist:
                    pass
            return redirect('/landing_page')
    else:
        form = RegistrationFormForm()
    return render(request, 'RegistrationForm.html', {'form': form})

@staff_member_required
def pending_associations(request):
    pending_users = UserAssociation.objects.filter(is_approved=False)
    return render(request, 'pending_associations.html', {'pending_users': pending_users})


@staff_member_required
def approve_association(request, association_id):
    association = UserAssociation.objects.get(pk=association_id)
    association.is_approved = True
    association.save()
    return redirect('pending_associations')


@login_required
def send_file(request):
    if request.method == 'POST':
        file = request.FILES.get('file')
        if file:
            File.objects.create(user=request.user, file=file)
            return redirect('/landing_page')
    return render(request, 'send_file.html')


@login_required
def create_card(request):
    if request.method == 'POST':
        form = CardForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                request.user.card
                form.add_error(None, "A card already exists for this user.")
            except User.card.RelatedObjectDoesNotExist:
                new_card = form.save(commit=False)
                new_card.user = request.user
                new_card.save()
                return redirect('/landing_page')
    else:
        form = CardForm()
    return render(request, 'create_card.html', {'card_form': form})


@login_required
def create_kyc(request):
    if request.method == 'POST':
        kyc_form = KYCForm(request.POST, request.FILES)
        if kyc_form.is_valid():
            user = request.user if request.user.is_authenticated else None
            uploaded_image = kyc_form.cleaned_data['uploaded_image']
            kyc_video = kyc_form.cleaned_data['kyc_video']
            phone_number = kyc_form.cleaned_data['phone_number']
            kyc = KYC(user=user, uploaded_image=uploaded_image, kyc_video=kyc_video, phone_number=phone_number)
            kyc.save()
            account_sid = 'AC87e2f3c11c67a2b0a6dd4f644d5900a7'
            auth_token = 'a76b9c54d676468919c4fa5a12785d3d'
            client = Client(account_sid, auth_token)
            try:
                message = client.messages.create(
                    body='KYC verification: Your photo and video have been received. Please wait for verification.',
                    from_='7565830698',
                    to=phone_number
                )
                messages.success(request, 'KYC verification message sent successfully.')
            except Exception as e:
                messages.error(request, f'Failed to send KYC verification message: {e}')
            return redirect('/landing_page')
        else:
            messages.error(request, 'Failed to submit KYC data. Please check the form entries.')
            return redirect('/landing_page')
    else:
        kyc_form = KYCForm()
    return render(request, 'create_kyc.html', {'kyc_form': kyc_form})

@login_required
def service1(request):
    return render(request, 'service1.html')

@login_required
def service2(request):
    return render(request, 'service2.html')

@login_required
def service3(request):
    return render(request, 'service3.html')

