# from datetime import timedelta, timezone
from urllib import request
import uuid
import zipfile
import pyrebase
from django import forms
from django.forms import CharField, EmailField
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User  # Import the User model at the top
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse, StreamingHttpResponse, HttpResponseNotFound, HttpResponseServerError
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.core.mail import send_mail, EmailMessage, get_connection
from django.core.cache import cache
from django.utils.module_loading import import_string
from django.conf import settings
from .models import KYC, File, TemporaryUser, UserAssociation, UserUpload, RegistrationForm, CustomGroup, CustomGroupAdmin#, TemporarilyLock
from .forms import CustomSignupForm, UserUploadForm, DeleteUploadForm, RegistrationFormForm, KYCForm, CardForm, GroupCreationForm, SubgroupSignupForm, PasswordResetForm
from twilio.rest import Client
from cryptography.fernet import Fernet
import os
import logging
from django.utils import timezone  # Import Django's timezone utility
from datetime import timedelta
from django.contrib.auth import update_session_auth_hash
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
import mimetypes
from docx import Document
from pptx import Presentation
import xml.etree.ElementTree as ET
from django.template.response import TemplateResponse
from django.core.files.base import ContentFile
import openpyxl  # To handle .xlsx files
import xlrd  # To handle .xls files
# import base64
from PyPDF2 import PdfReader
from django.core.files.storage import FileSystemStorage
from django.utils.html import escape
from pdf2image import convert_from_path
from PIL import Image
import io
import shutil
from .tasks import process_file_upload  # import your Celery task
from django.views.decorators.cache import never_cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import cache_page
from django.views.decorators.cache import cache_control
from io import BytesIO

#pwa
from django.contrib.staticfiles import finders
from django.urls import get_resolver
from django.conf import settings


# Allauth social authentication requirements
from allauth.socialaccount.models import SocialLogin
from allauth.socialaccount.providers.google.provider import GoogleProvider
from allauth.socialaccount.helpers import complete_social_login

# Google security validation library
from google.oauth2 import id_token
from google.auth.transport import requests

logger = logging.getLogger(__name__)



firebaseConfig={
    'apiKey': "AIzaSyCN7s6q2iX84wAa-bcADtojDbRKRsK5UTk",
    'authDomain': "authporp.firebaseapp.com",
    'projectId': "authporp",
    'storageBucket': "authporp.appspot.com",
    'messagingSenderId': "746007263598",
    'appId': "1:746007263598:web:1d9cbb363e41cba3d3e97f",
    'measurementId': "G-MQ4Q1F4FCE",
    "databaseURL": "",
}

firebase= pyrebase.initialize_app(firebaseConfig)
auth=firebase.auth()



'''
def pwa_cache_manifest(request):
    """
    Dynamically builds a list of URLs for the PWA to cache:
    - All routes from allowed apps (user_profile, only_message, notion)
    - All static files from collectstatic
    - Homepage and offline fallback
    """
    allowed_apps = {"user_profile", "only_message", "notion"}
    urls = set()

    # 1️⃣ollect all page URLs from selected apps
    resolver = get_resolver()
    for pattern in resolver.url_patterns:
        if hasattr(pattern, "callback") and pattern.callback:
            module = getattr(pattern.callback, "__module__", "")
            if any(app in module for app in allowed_apps):
                path_str = f"/{pattern.pattern}".replace("^", "").replace("$", "")
                if not path_str.endswith("/"):
                    path_str += "/"
                urls.add(path_str)

    #ollect all static files from Django's finders
    static_urls = []
    for finder in finders.get_finders():
        for path, storage in finder.list([]):
            url = os.path.join(settings.STATIC_URL, path).replace("\\", "/")
            static_urls.append(url)
    urls.update(static_urls)

    # dd essential routes manually
    urls.add("/")  # Homepage
    urls.add("/offline/")  # Offline fallback (if implemented)

    # lean and sort
    urls = sorted(urls)

    return JsonResponse(urls, safe=False)
'''



def home(request):
    return render(request, 'home.html')

@cache_control(public=True, max_age=86400, s_maxage=7200, must_revalidate=True)
def TermAndCondition(request):
    return render(request, 'TermAndCondition.html')


def send_confirmation_email(user):
    subject = "Welcome to SOCYFIE Login!"
    message = f"Hello {user.first_name},\nWelcome to SOCYFIE!\nThank you for being a part of our community."
    email_from = settings.EMAIL_HOST_USER
    recipient_list = [user.email]
    send_mail(subject, message, email_from, recipient_list)


from service_auth.only_message.encryption_utils import generate_key_pair, serialize_key
@csrf_exempt
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
                #login(request, user_model)
                #  NEW EXPLICIT LINE:
                login(request, user_model, backend='django.contrib.auth.backends.ModelBackend')

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


'''
@csrf_exempt
#@never_cache
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def login_view(request):
    if request.user.is_authenticated:

        #return redirect('/following_media')  
        return redirect('/feed')  

    if request.method == 'POST':
        username_or_email = request.POST['username'].strip()
        password = request.POST['pass1']
        remember_me = request.POST.get('remember_me')  # This is a checkbox in your HTML

        try:
            # Check if the input is an email or username
            if '@' in username_or_email:
                # Authenticate with email
                user = User.objects.get(email=username_or_email)
                username = user.username
            else:
                # Authenticate with username
                username = username_or_email
                user = User.objects.get(username=username)

            # Firebase authentication: Check if the provided credentials are correct in Firebase
            try:
                firebase_user = auth.sign_in_with_email_and_password(user.email, password)

                # At this point, the password matches Firebase. Update Django's password with Firebase password.
                user.set_password(password)  # Sync the Firebase password with Django's password
                user.save()

                # Authenticate the user in Django with the updated password
                user = authenticate(request, username=username, password=password)

                if user is not None:
                    # Log the user in Django
                    login(request, user)

                    # Ensure the session remains intact after password update
                    update_session_auth_hash(request, user)
                    # Set session expiry based on "remember me"
                    if not remember_me:
                        request.session.set_expiry(0)  # Session expires on browser/app close
                    else:
                        request.session.set_expiry(60 * 60 * 24 * 100)  # 14 days

                    #response = redirect('/following_media')  # Default redirect
                    response = redirect('/feed')  # Default redirect


                    # Redirect based on user roles
                    if CustomGroupAdmin.objects.filter(user=user).exists():
                        return redirect('/subgroup_landing_page')
                    elif user.is_staff:
                        return redirect('/super_user_landing_page')

                    # Set session/cookie/cache
                    response.set_cookie('username', username)
                    cache.set(f'user_{user.id}', username)
                    return response  

            except Exception as firebase_error:
                # Handle Firebase authentication errors
                error_message = str(firebase_error)
                if "EMAIL_NOT_FOUND" in error_message:
                    messages.error(request, "No account found with this email.")
                elif "INVALID_PASSWORD" in error_message:
                    messages.error(request, "The password is incorrect. Please try again.")
                else:
                    messages.error(request, f"Firebase error: {error_message}")

        except User.DoesNotExist:
            messages.error(request, 'Invalid username or email')

        # Group-based authentication (if necessary)
        try:
            group = CustomGroup.objects.get(name=username_or_email)
            user = group.users.first()
            if user:
                login(request, user)
                # Set session expiry based on "remember me" here as well
                if not remember_me:
                    request.session.set_expiry(0)
                else:
                    request.session.set_expiry(60 * 60 * 24 * 100)

                request.session['association_name'] = username_or_email
                request.session['user_id'] = user.id
                cache.set(f'user_{user.id}', username_or_email)
                return redirect('/landing_page')
        except CustomGroup.DoesNotExist:
            #pass
            messages.error(request, 'Invalid username, email, or group name.')

        except Exception as e:
            messages.error(request, f"Login failed: {str(e)}")

        return render(request, 'login_view.html')

    else:
        return render(request, 'login_view.html')
'''



@csrf_exempt
#@never_cache
@cache_control(public=True, max_age=864000, s_maxage=864050)
# must_revalidate=True)
def login_view(request):
    if request.user.is_authenticated:

        #return redirect('/following_media')  
        return redirect('/feed')  

    if request.method == 'POST':
        username_or_email = request.POST['username'].strip()
        password = request.POST['pass1']
        remember_me = request.POST.get('remember_me')  # This is a checkbox in your HTML

        try:
            # Check if the input is an email or username
            if '@' in username_or_email:
                # Authenticate with email
                user = User.objects.get(email=username_or_email)
                username = user.username
            else:
                # Authenticate with username
                username = username_or_email
                user = User.objects.get(username=username)

            # Firebase authentication: Check if the provided credentials are correct in Firebase
            try:
                firebase_user = auth.sign_in_with_email_and_password(user.email, password)

                # At this point, the password matches Firebase. Update Django's password with Firebase password.
                #user.set_password(password)  # Sync the Firebase password with Django's password
                #user.save()

                # Authenticate the user in Django with the updated password
                #user = authenticate(request, username=username, password=password)

                # Retrieve the Django user
                user = User.objects.get(username=username)

                if user is not None:
                    # Log the user in Django
                    #login(request, user)
                    #  NEW EXPLICIT LINE:
                    login(request, user, backend='django.contrib.auth.backends.ModelBackend')

                    # Ensure the session remains intact after password update
                    #update_session_auth_hash(request, user)
                    # Set session expiry based on "remember me"
                    if not remember_me:
                        request.session.set_expiry(0)  # Session expires on browser/app close
                    else:
                        request.session.set_expiry(60 * 60 * 24 * 100)  # 14 days

                    #response = redirect('/following_media')  # Default redirect
                    response = redirect('/feed')  # Default redirect


                    # Redirect based on user roles
                    if CustomGroupAdmin.objects.filter(user=user).exists():
                        return redirect('/subgroup_landing_page')
                    elif user.is_staff:
                        return redirect('/super_user_landing_page')

                    # Set session/cookie/cache
                    response.set_cookie('username', username)
                    cache.set(f'user_{user.id}', username)
                    return response  

            except Exception as firebase_error:
                # Handle Firebase authentication errors
                error_message = str(firebase_error)
                if "EMAIL_NOT_FOUND" in error_message:
                    messages.error(request, "No account found with this email.")
                elif "INVALID_PASSWORD" in error_message:
                    messages.error(request, "The password is incorrect. Please try again.")
                else:
                    messages.error(request, f"Firebase error: {error_message}")

        except User.DoesNotExist:
            messages.error(request, 'Invalid username or email')

        # Group-based authentication (if necessary)
        try:
            group = CustomGroup.objects.get(name=username_or_email)
            user = group.users.first()
            if user:
                #login(request, user)
                #  NEW EXPLICIT LINE:
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')

                # Set session expiry based on "remember me" here as well
                if not remember_me:
                    request.session.set_expiry(0)
                else:
                    request.session.set_expiry(60 * 60 * 24 * 100)

                request.session['association_name'] = username_or_email
                request.session['user_id'] = user.id
                cache.set(f'user_{user.id}', username_or_email)
                return redirect('/landing_page')
        except CustomGroup.DoesNotExist:
            #pass
            messages.error(request, 'Invalid username, email, or group name.')

        except Exception as e:
            messages.error(request, f"Login failed: {str(e)}")

        return render(request, 'login_view.html')

    else:
        return render(request, 'login_view.html')



@csrf_exempt
def google_one_tap_callback(request):
    """
    Handles the backend token verification payload posted securely 
    by the frontend Google One-Tap prompt component.
    """
    if request.method != 'POST':
        return redirect('/')

    # 1. Robustly extract the token from Google's redirect POST payload fields
    token = request.POST.get('credential')
    
    # Fallback check if the data arrived as a raw JSON payload body
    if not token and request.body:
        try:
            body_data = json.loads(request.body.decode('utf-8'))
            token = body_data.get('credential')
        except Exception:
            pass

    if not token:
        messages.error(request, "Google verification token missing.")
        return redirect('/')

    try:
        # 2. Fetch your Google Client ID dynamically from settings
        google_client_id = settings.SOCIALACCOUNT_PROVIDERS['google']['APP']['client_id']

        from google.auth import jwt
        # 3. Cryptographically verify the token with Google public keys and add clock tolerance
        idinfo = id_token.verify_oauth2_token(
            token, 
            requests.Request(), 
            google_client_id,
            #clock_skew=60 # Permits a 60-second time drift between your server and Google
        )

        email = idinfo.get('email')
        if not email:
            messages.error(request, "Unable to extract email from your Google Profile.")
            return redirect('/')

        first_name = idinfo.get('given_name', '')
        last_name = idinfo.get('family_name', '')
        
        # 4. Synchronize user profile context with Firebase and Django
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # A) Create placeholder account inside Firebase first to maintain architecture sync
            try:
                random_password = User.objects.make_random_password(length=16)
                # Triggers your existing Firebase auth setup (e.g. pyrebase/firebase-admin)
                auth.create_user_with_email_and_password(email, random_password)
            except Exception as fb_err:
                # If account exists natively in Firebase but not Django, bypass error gracefully
                if "EMAIL_EXISTS" not in str(fb_err):
                    raise fb_err

            # B) Build a clean username targeting your exact alphanumeric Regex pattern restrictions
            email_prefix = email.split('@')[0]
            clean_username = "".join(c for c in email_prefix if c.isalnum() or c in '._-')[:20]
            
            # Enforce uniqueness if the generated username is already taken
            if User.objects.filter(username=clean_username).exists():
                clean_username = f"{clean_username}_{uuid.uuid4().hex[:4]}"

            # C) Create the User record in your local Django database
            user = User.objects.create_user(
                username=clean_username,
                email=email,
                first_name=first_name,
                last_name=last_name
            )

        # 5. Hand off execution to Django's login system using your explicit backend path
        # This completely resolves your previous multiple backend configuration conflict
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')

        # 6. Replicate your exact "Remember Me" session tracking duration (14 days)
        request.session.set_expiry(60 * 60 * 24 * 14)  
        
        # 7. Setup the landing redirect path route
        response = redirect('/feed')

        # 8. Set the custom tracking cookie on the browser frontend matching your login view
        response.set_cookie(
            'username', 
            user.username, 
            max_age=60 * 60 * 24 * 14, # 14 days matching session
            httponly=False,            # Allow frontend JS tracking logic to read
            samesite='Lax'
        )
        
        # Optional: Synchronize your custom cache layer if active
        # cache.set(f'user_{user.id}', user.username)
            
        return response

    except KeyError:
        messages.error(request, "Google APP configurations missing inside settings.py.")
        return redirect('/')

    except ValueError:
        messages.error(request, "Security signature validation failed for Google payload.")
        return redirect('/')

    except Exception as e:
        messages.error(request, f"One-Tap Login crashed: {str(e)}")
        return redirect('/')



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
    request.session.flush()
    logout(request)
   # request.session.flush()
    return redirect('/')



def password_reset(request):
    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            username_or_email = form.cleaned_data['username_or_email']
            try:
                # Check if username_or_email is a username or email
                if '@' in username_or_email:
                    # It's an email
                    user = User.objects.get(email=username_or_email)
                else:
                    # It's a username
                    user = User.objects.get(username=username_or_email)
                # Send Firebase password reset email
                auth.send_password_reset_email(user.email)
                messages.success(request, 'A password reset link has been sent to your email.')
                return redirect('/login/')
            except User.DoesNotExist:
                messages.error(request, "No account found with this username or email address.")
            except Exception as e:
                error_message = str(e)
                messages.error(request, f"Error: {error_message}")
        else:
            messages.error(request, 'Please provide a valid username or email.')
    else:
        form = PasswordResetForm()
        if request.user.is_authenticated:
            email = request.user.email
            form.fields['username_or_email'].initial = email
            form.fields['username_or_email'].widget = forms.HiddenInput()

    return render(request, 'password_reset.html', {'form': form})

@login_required
@cache_control(public=True, max_age=864000, s_maxage=864050)
# must_revalidate=True)
def landing_page(request):
    cache_key = f'user_{request.user.id}_username'
    user_username = cache.get(cache_key)
    #user_username = cache.get(f'user_{request.user.id}')
    if not user_username:
        user_username = request.user.username
        cache.set(cache_key, user_username, timeout=60 * 60 * 24 * 10)  # Cache for 1 day
        #cache.set(f'user_{request.user.id}', user_username, timeout=3600)
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


def buy_storage(request):
    return render(request, 'buy_storage.html')


@login_required
@cache_page(60 * 2)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
#@cache_control(public=True, max_age=120, s_maxage=120)
def upload_document(request):
    if request.method == 'POST':
        form = UserUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            try:
                upload_instance = form.save(commit=False)
                upload_instance.user = request.user
                upload_instance.save()

                # Trigger async post-upload processing (encryption, MIME check, etc.)
                process_file_upload.delay(upload_instance.id)

                # Determine where to redirect user based on role
                is_admin = CustomGroupAdmin.objects.filter(user=request.user).exists()
                redirect_url = '/subgroup_landing_page' if is_admin else '/landing_page'

                return JsonResponse({'status': 'success', 'redirect_url': redirect_url})
            
            except Exception as e:
                logger.exception("Failed to save uploaded file or enqueue processing.")
                return JsonResponse({'status': 'error', 'message': 'Upload failed. Please try again.'}, status=500)

        else:
            logger.warning(f"Upload form validation failed: {form.errors}")
            return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)

    # GET request – render the form page
    return render(request, 'upload_document.html', {'form': UserUploadForm()})



@cache_page(60 * 10)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def view_video_page(request, upload_id):
    try:
        user_id = request.user.id

        # Define cache keys
        cache_key_username = f'user_{user_id}_username'
        cache_key_video_mime = f'user_{user_id}_upload_{upload_id}_mime'
        cache_key_video_filename = f'user_{user_id}_upload_{upload_id}_filename'

        # Cache username
        user_username = cache.get(cache_key_username)
        if not user_username:
            user_username = request.user.username
            cache.set(cache_key_username, user_username, timeout=60 * 60 * 24)

        # Fetch upload
        upload = get_object_or_404(UserUpload, id=upload_id, user=request.user)

        # Cache MIME type using file name instead of file path
        mime_type = cache.get(cache_key_video_mime)
        if not mime_type:
            mime_type, _ = mimetypes.guess_type(upload.file.name)
            if not mime_type:
                mime_type = "application/octet-stream"
            cache.set(cache_key_video_mime, mime_type, timeout=60 * 60)

        # Cache file name
        file_name = cache.get(cache_key_video_filename)
        if not file_name:
            # Prefer original file name if stored, otherwise fallback to name from storage
            file_name = upload.file_name or os.path.basename(upload.file.name)
            cache.set(cache_key_video_filename, file_name, timeout=60 * 60 * 12)

        return render(request, 'view_video.html', {
            'upload': upload,
            'file_name': file_name,
            'mime_type': mime_type,
        })

    except Exception as e:
        logger.error(f"Error in view_video_page: {e}")
        return HttpResponseServerError("An error occurred while processing your request.")




from django.core.files.storage import default_storage

@cache_page(60 * 10)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def view_media(request, upload_id):
    try:
        cache_key_username = f'user_{request.user.id}_username'
        cache_key_mime = f'user_{request.user.id}_upload_{upload_id}_mime'

        user_username = cache.get(cache_key_username)
        if not user_username:
            user_username = request.user.username
            cache.set(cache_key_username, user_username, 60 * 60 * 24)

        upload = get_object_or_404(UserUpload, id=upload_id, user=request.user)

        if not upload.encryption_key:
            logger.error(f"Encryption key not found for file ID {upload_id}")
            return HttpResponseServerError("Encryption key is missing.")

        try:
            fernet = Fernet(upload.encryption_key.encode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to initialize Fernet: {e}")
            return HttpResponseServerError("Could not initialize decryption.")

        # Try to read encrypted file data using Django's file storage API
        try:
            file_obj = upload.file.open('rb')
            encrypted_data = file_obj.read()
            file_obj.close()
        except Exception as e:
            logger.error(f"File not accessible: {e}")
            return HttpResponseNotFound("Media file not found.")

        # MIME type detection via name
        mime_type = cache.get(cache_key_mime)
        if not mime_type:
            mime_type, _ = mimetypes.guess_type(upload.file.name)
            if not mime_type:
                mime_type = "application/octet-stream"
            cache.set(cache_key_mime, mime_type, timeout=60 * 60)

        if not (mime_type.startswith("image/") or mime_type.startswith("video/")):
            logger.warning(f"Unsupported preview MIME type: {mime_type}")
            return HttpResponse("Unsupported file type for inline preview.", status=415)

        try:
            decrypted_data = fernet.decrypt(encrypted_data)
        except Exception as e:
            logger.error(f"Error during decryption: {e}")
            return HttpResponseServerError("Failed to decrypt media.")

        return HttpResponse(decrypted_data, content_type=mime_type)

    except Exception as e:
        logger.error(f"Unhandled exception in view_media: {e}")
        return HttpResponseServerError("An error occurred while processing media.")



@cache_page(60 * 10)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def view_file(request, upload_id):
    try:
        # Fetch the uploaded file for the authenticated user
        upload = get_object_or_404(UserUpload, id=upload_id, user=request.user)

        if not upload.encryption_key:
            logger.error(f"Encryption key not found for file with ID {upload_id}")
            return HttpResponseServerError("Encryption key not found for this file.")

        try:
            fernet = Fernet(upload.encryption_key.encode('utf-8'))
        except Exception as e:
            logger.error(f"Error initializing Fernet cipher: {e}")
            return HttpResponseServerError("Failed to initialize decryption.")

        try:
            # Open file using Django's storage backend (works for R2 and local)
            with upload.file.open('rb') as encrypted_file:
                encrypted_file_data = encrypted_file.read()
        except Exception as e:
            logger.error(f"File not accessible: {e}")
            return HttpResponseNotFound("File not found.")

        # Detect MIME type using file name
        mime_type, _ = mimetypes.guess_type(upload.file.name)
        if not mime_type:
            mime_type = 'application/octet-stream'

        try:
            decrypted_file_data = fernet.decrypt(encrypted_file_data)

            # Return as streaming response
            response = StreamingHttpResponse(
                iter([decrypted_file_data]),
                content_type=mime_type
            )
            response['Content-Disposition'] = f'attachment; filename="{upload.file_name}"'
            return response

        except Exception as e:
            logger.error(f"Error during file decryption: {e}")
            return HttpResponseServerError("Error decrypting file.")

    except Exception as e:
        logger.error(f"Unhandled exception in view_file: {e}")
        return HttpResponseServerError("An error occurred while processing your request.")


@cache_page(60 * 10)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def view_pdf_file(request, upload_id):
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

        # Check if it's a .pdf file
        if not upload.file.name.endswith('.pdf'):
            logger.error(f"Unsupported file type: {upload.file.name}")
            return HttpResponseServerError("Unsupported file type.")

        try:
            # Read and decrypt directly from cloud storage
            with upload.file.open('rb') as encrypted_file:
                encrypted_file_data = encrypted_file.read()

            decrypted_file_data = fernet.decrypt(encrypted_file_data)

            # Use BytesIO to serve file directly from memory
            buffer = BytesIO(decrypted_file_data)
            response = HttpResponse(buffer, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{upload.file_name}"'
            return response

        except Exception as e:
            logger.error(f"Error reading .pdf file: {e}")
            return HttpResponseServerError("Error reading .pdf file.")

    except Exception as e:
        logger.error(f"Unhandled exception in view_pdf_file: {e}")
        return HttpResponseServerError("An error occurred while processing your request.")


@cache_page(60 * 10)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def view_docx_file(request, upload_id):
    try:
        # Fetch uploaded file for authenticated user
        upload = get_object_or_404(UserUpload, id=upload_id, user=request.user)

        if not upload.encryption_key:
            logger.error(f"Encryption key not found for file with ID {upload_id}")
            return HttpResponseServerError("Encryption key not found for this file.")

        try:
            fernet = Fernet(upload.encryption_key.encode('utf-8'))
        except Exception as e:
            logger.error(f"Error initializing Fernet cipher: {e}")
            return HttpResponseServerError("Failed to initialize decryption.")

        # Check file extension
        if not upload.file.name.endswith('.docx'):
            logger.error(f"Unsupported file type: {upload.file.name}")
            return HttpResponseServerError("Unsupported file type.")

        try:
            # Read encrypted data from storage backend (e.g., S3)
            with upload.file.open('rb') as encrypted_file:
                encrypted_file_data = encrypted_file.read()

            # Decrypt data
            decrypted_file_data = fernet.decrypt(encrypted_file_data)

            # Load decrypted .docx content using BytesIO (no temp file needed)
            docx_stream = BytesIO(decrypted_file_data)
            document = Document(docx_stream)

            # Extract paragraphs as HTML
            docx_content = "".join(f"<p>{para.text}</p>" for para in document.paragraphs)

            return render(request, 'view_docx.html', {
                'docx_content': docx_content,
                'file_name': upload.file_name,
            })

        except Exception as e:
            logger.error(f"Error reading .docx file: {e}")
            return HttpResponseServerError("Error reading .docx file.")

    except Exception as e:
        logger.error(f"Unhandled exception in view_docx_file: {e}")
        return HttpResponseServerError("An error occurred while processing your request.")


@cache_page(60 * 10)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def view_pptx_file(request, upload_id):
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

        if not upload.file.name.endswith('.pptx'):
            logger.error(f"Unsupported file type: {upload.file.name}")
            return HttpResponseServerError("Unsupported file type.")

        try:
            # Read and decrypt the file in memory
            with upload.file.open('rb') as encrypted_file:
                encrypted_file_data = encrypted_file.read()

            decrypted_file_data = fernet.decrypt(encrypted_file_data)

            # Use BytesIO for in-memory loading with python-pptx
            pptx_io = BytesIO(decrypted_file_data)
            presentation = Presentation(pptx_io)

            # Extract text content from slides
            pptx_content = ""
            for slide_number, slide in enumerate(presentation.slides, start=1):
                pptx_content += f"<h3>Slide {slide_number}</h3>"
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        pptx_content += f"<p>{shape.text}</p>"

            return render(request, 'view_docx.html', {
                'pptx_content': pptx_content,
                'file_name': upload.file_name
            })

        except Exception as e:
            logger.error(f"Error reading .pptx file: {e}")
            return HttpResponseServerError("Error reading .pptx file.")

    except Exception as e:
        logger.error(f"Unhandled exception in view_pptx_file: {e}")
        return HttpResponseServerError("An error occurred while processing your request.")



@cache_page(60 * 10)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def is_valid_excel_file(file_path):
    # Supported MIME types for Excel files
    excel_mime_types = [
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
        'application/vnd.ms-excel.sheet.macroEnabled.12',  # .xlsm
        'application/vnd.openxmlformats-officedocument.spreadsheetml.template',  # .xltx
        'application/vnd.ms-excel.template.macroEnabled.12'  # .xltm
    ]
    
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type in excel_mime_types



@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def view_xml_file(request, upload_id):
    try:

        # Fetch the uploaded file record for the authenticated user
        upload = get_object_or_404(UserUpload, id=upload_id, user=request.user)

        # Ensure the file has an encryption key
        if not upload.encryption_key:
            logger.error(f"Encryption key not found for file with ID {upload_id}")
            return HttpResponseServerError("Encryption key not found for this file.")

        try:
            # Initialize the Fernet cipher for decryption using the encryption key
            fernet = Fernet(upload.encryption_key.encode('utf-8'))
        except Exception as e:
            logger.error(f"Error initializing Fernet cipher: {e}")
            return HttpResponseServerError("Failed to initialize decryption.")

        # Check if the file exists on the server
        file_path = upload.file.path
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return HttpResponseNotFound("File not found")

        # Get the file extension and handle accordingly
        file_extension = os.path.splitext(file_path)[1].lower()

        # Decrypt and handle the file based on its extension
        if file_extension == '.xml':
            return handle_xml_or_xlsx_file(file_path, fernet, upload, file_type='xml')
        elif file_extension == '.xlsx' or file_extension == '.xls':
            return handle_xml_or_xlsx_file(file_path, fernet, upload, file_type=file_extension)
        else:
            logger.error(f"Unsupported file type: {file_path}")
            return HttpResponseServerError("Unsupported file type.")

    except Exception as e:
        logger.error(f"Unhandled exception in view_xml_file: {e}")
        return HttpResponseServerError("An error occurred while processing your request.")


@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def handle_xml_or_xlsx_file(file_path, fernet, upload, file_type):
    """Handles XML, XLS, and XLSX file decryption and rendering."""
    try:

        # Read and decrypt the entire file
        with open(file_path, 'rb') as encrypted_file:
            encrypted_file_data = encrypted_file.read()

        # Write the decrypted content to a temporary file for processing
        decrypted_file_path = os.path.join('/tmp', f"decrypted_{upload.file_name}")
        with open(decrypted_file_path, 'wb') as decrypted_file:
            decrypted_file.write(fernet.decrypt(encrypted_file_data))

        # Process based on file type
        if file_type == 'xml':
            # Handle XML file
            return handle_xml_file(decrypted_file_path, upload)

        elif file_type == '.xlsx':
            # Handle XLSX file
            return handle_xlsx_file(decrypted_file_path, upload)

        elif file_type == '.xls':
            # Handle XLS file using xlrd
            return handle_xls_file(decrypted_file_path, upload)

        else:
            logger.error("Unsupported file type provided.")
            return HttpResponseServerError("Unsupported file type.")

    except Exception as e:
        logger.error(f"Error decrypting {file_type} file: {e}")
        return HttpResponseServerError(f"Error decrypting {file_type} file.")
    finally:
        # Clean up the temporary decrypted file if it exists
        if os.path.exists(decrypted_file_path):
            os.remove(decrypted_file_path)


@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def handle_xml_file(decrypted_file_path, upload):
    """Handles the XML file content."""
    try:

        # Parse the XML content
        with open(decrypted_file_path, 'r', encoding='utf-8') as decrypted_file:
            xml_data = decrypted_file.read()

        root = ET.fromstring(xml_data)

        # Convert XML content to a string for display
        xml_content = ET.tostring(root, encoding='unicode', method='xml')

        # Render the content in an HTML template
        return render(request, 'view_docx.html', {
            'xml_content': xml_content,
            'file_name': upload.file_name
        })

    except ET.ParseError as e:
        logger.error(f"Error parsing XML file: {e}")
        return HttpResponseServerError("Error parsing the XML file.")


@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def handle_xlsx_file(decrypted_file_path, upload):
    """Handles the XLSX file content using openpyxl."""
    try:

        # Log the decrypted file path to ensure decryption is happening
        logger.info(f"Decrypted file path: {decrypted_file_path}")
        
        # Check the file size to make sure it's a valid Excel file size
        file_size = os.path.getsize(decrypted_file_path)
        logger.info(f"Decrypted file size: {file_size} bytes")
        
        # Open the decrypted Excel file using openpyxl
        workbook = openpyxl.load_workbook(decrypted_file_path)
        sheet = workbook.active

        # Collect data from the first sheet
        excel_data = []
        for row in sheet.iter_rows(values_only=True):
            excel_data.append(row)

        # Render the content in an HTML template
        return render(request, 'view_docx.html', {
            'excel_data': excel_data,
            'file_name': upload.file_name
        })

    except Exception as e:
        logger.error(f"Error reading Excel file (.xlsx): {e}")
        return HttpResponseServerError("Error reading Excel file (.xlsx).")



@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def handle_xls_file(decrypted_file_path, upload):
    """Handles the older .xls file format using xlrd."""
    try:

        # Open the decrypted Excel file using xlrd
        workbook = xlrd.open_workbook(decrypted_file_path)
        sheet = workbook.sheet_by_index(0)

        # Collect data from the first sheet
        excel_data = []
        for row_num in range(sheet.nrows):
            row = sheet.row_values(row_num)
            excel_data.append(row)

        # Render the content in an HTML template
        return render(request, 'view_docx.html', {
            'excel_data': excel_data,
            'file_name': upload.file_name
        })

    except Exception as e:
        logger.error(f"Error reading Excel file (.xls): {e}")
        return HttpResponseServerError("Error reading Excel file (.xls).")


@cache_page(60 * 10)
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def view_text_file(request, upload_id):
    try:
        # Fetch the uploaded file record
        upload = get_object_or_404(UserUpload, id=upload_id, user=request.user)

        # Ensure encryption key exists
        if not upload.encryption_key: 
            logger.error(f"Encryption key not found for file with ID {upload_id}")
            return HttpResponseServerError("Encryption key not found for this file.")

        # Initialize Fernet cipher
        try:
            fernet = Fernet(upload.encryption_key.encode('utf-8'))
        except Exception as e:
            logger.error(f"Error initializing Fernet cipher: {e}")
            return HttpResponseServerError("Failed to initialize decryption.")

        # Check file extension validity
        file_extension = os.path.splitext(upload.file.name)[1].lower()
        if file_extension not in ['.txt', '.py', '.js']:
            logger.error(f"Unsupported text file type: {file_extension}")
            return HttpResponseServerError("Unsupported text file type.")

        # Read and decrypt the file in memory
        try:
            with upload.file.open('rb') as encrypted_file:
                encrypted_data = encrypted_file.read()

            decrypted_data = fernet.decrypt(encrypted_data).decode('utf-8')

            # Identify type for syntax highlighting
            if file_extension == '.py':
                file_type = 'python'
            elif file_extension == '.js':
                file_type = 'javascript'
            else:
                file_type = 'text'

            return render(request, 'view_docx.html', {
                'txt_content': decrypted_data,
                'file_name': upload.file_name,
                'file_type': file_type
            })

        except Exception as e:
            logger.error(f"Error reading or decrypting text file: {e}")
            return HttpResponseServerError("Error reading text file.")

    except Exception as e:
        logger.error(f"Unhandled exception in view_text_file: {e}")
        return HttpResponseServerError("An error occurred while processing your request.")


@login_required
def upload_folder(request):
    if request.method == 'POST':
        form = UserUploadForm(request.POST, request.FILES)
        folder_files = request.FILES.getlist('folder_files')  # Expecting multiple files
        folder_name = request.POST.get('folder_name', 'uploaded_folder')

        if folder_files and form.is_valid():
            form.instance.user = request.user

            # Step 1: Create a zip archive from the files
            temp_zip_path = f'/tmp/{folder_name}.zip'
            with zipfile.ZipFile(temp_zip_path, 'w') as zipf:
                for file in folder_files:
                    zipf.writestr(file.name, file.read())

            # Step 2: Generate an encryption key and encrypt the archive
            encryption_key = Fernet.generate_key()
            fernet = Fernet(encryption_key)

            with open(temp_zip_path, 'rb') as zip_file:
                encrypted_data = fernet.encrypt(zip_file.read())

            # Step 3: Save the encrypted archive to the model
            form.instance.file = ContentFile(encrypted_data, f'{folder_name}.zip')
            form.instance.file_name = f'{folder_name}.zip'
            form.instance.encryption_key = encryption_key.decode('utf-8')
            form.instance.is_folder = True

            try:
                form.save()
            except ValueError:
                messages.error(request, "Storage full. Please buy more storage.")
                return redirect('/buy_storage')

            # Step 4: Clean up temporary files
            os.remove(temp_zip_path)

            # Redirect after successful upload
            if CustomGroupAdmin.objects.filter(user=request.user).exists():
                return redirect('/subgroup_landing_page')
            else:
                return redirect('/landing_page')
    else:
        form = UserUploadForm()

    return render(request, 'upload_folder.html', {'form': form})



@login_required
def view_folder(request, upload_id):
    try:
        # Fetch the folder record
        upload = get_object_or_404(UserUpload, id=upload_id, user=request.user, is_folder=True)

        if not upload.encryption_key:
            logger.error(f"Encryption key missing for upload ID {upload_id}")
            return HttpResponseServerError("Encryption key missing.")

        # Decrypt the folder archive
        try:
            fernet = Fernet(upload.encryption_key.encode('utf-8'))
            encrypted_data = upload.file.read()
            decrypted_data = fernet.decrypt(encrypted_data)
        except Exception as e:
            logger.error(f"Decryption failed for upload ID {upload_id}: {e}")
            return HttpResponseServerError("Decryption failed.")

        # Extract the archive to a temporary location
        temp_extract_path = f'/tmp/{upload.file_name.replace(".zip", "")}'
        os.makedirs(temp_extract_path, exist_ok=True)

        temp_zip_path = f'{temp_extract_path}.zip'
        with open(temp_zip_path, 'wb') as temp_zip:
            temp_zip.write(decrypted_data)

        with zipfile.ZipFile(temp_zip_path, 'r') as zipf:
            zipf.extractall(temp_extract_path)

        os.remove(temp_zip_path)

        # List extracted files and provide links to view/download
        file_links = []
        for root, _, files in os.walk(temp_extract_path):
            for file in files:
                file_path = os.path.join(root, file)
                file_links.append(file_path.replace('/tmp/', '/tmp/'))

        return render(request, 'view_folder.html', {'files': file_links, 'upload': upload})

    except Exception as e:
        logger.error(f"Unhandled exception in view_folder: {e}")
        return HttpResponseServerError("An error occurred while processing the folder.")
    finally:
        # Clean up extracted files after serving the response
        if 'temp_extract_path' in locals():
            shutil.rmtree(temp_extract_path, ignore_errors=True)




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


