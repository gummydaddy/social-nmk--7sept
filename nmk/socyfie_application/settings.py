"""
Django settings for nmk project.

Generated by 'django-admin startproject' using Django 4.2.11.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""

from pathlib import Path
import os
from cryptography.fernet import Fernet
import environ



# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/


# settings.py
APP_NAME = "Socyfie"


ALLOWED_HOSTS = ['127.0.0.1', "8080", "localhost", "www.socyfie.com"]

SITE_ID = 2

APPEND_SLASH = True


# # Read the encryption key from environment variable
# ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY')

# if not ENCRYPTION_KEY:
#     raise ValueError("No ENCRYPTION_KEY set for Flask application. Did you forget to set it?")

# ..-----...-------...

# Convert it to bytes if it's not already
# new look ENCRYPTION_KEY = ENCRYPTION_KEY.encode()

# # new
# env = environ.Env()
# environ.Env.read_env()  # Reads the .env file

# # Read the encryption key from the environment
# ENCRYPTION_KEY = env('ENCRYPTION_KEY').encode()



# Application definition
INSTALLED_APPS = [

    "django.contrib.admin",
    "django.contrib.auth",
    'django.contrib.sites',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',    
    'allauth.socialaccount.providers.google',    
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 'django-select2',
    "rest_framework",
    
    # 'user_profile.apps.UserProfileConfig',
    'channels',
    'social_django',
    'sslserver',
    'crispy_forms',
    'celery',
    'cryptography',
    'redis',
    'pyrebase',
    'bleach',
    # 'pillow',
    # 'python-docx',
    # 'python-pptx',
    'openpyxl',
    'xlrd',
    # 'pyPDF2',
    'pdf2image',
    'moviepy',
    # 'ffmpeg',
    'twilio',
    'six',



    # 'service_auth.only_coin',
    'nmk_chain',
    "service_auth.only_card",
    'service_auth.notion',
    'service_auth.user_profile',
    'service_auth.only_message',


]


SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        "AUTH_PARAMS":{"access_type": "online"}
    }
}

# WSGI_APPLICATION = "socyfie_application.wsgi.application"
# new29
ASGI_APPLICATION = 'socyfie_application.asgi.application'  


CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'asgi_redis.RedisChannelLayer',
        'CONFIG': {
            'hosts': [('localhost', 6379)],
        },
        'ROUTING': 'service_auth.only_message_channels.routing.channel_routing',
    }
}


CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': '127.0.0.1:6379/1',  # For Redis
        # 'LOCATION': '127.0.0.1:11211',  # For Memcached
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'DB': 1,  # Use a different database
        },
        'KEY_PREFIX': 'example caches'
    }
}


# T_BIRD_CONFIG = {
#     'HOST': 't-bird-host',
#     'PORT': 1234,
#     'USER': 'your_username',
#     'PASSWORD': 'your_password',
# }


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}

# new29
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

MIDDLEWARE = [

    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    'service_auth.only_card.middleware.SubgroupApprovalMiddleware',
    'service_auth.only_message.middleware.UpdateLastActivityMiddleware',
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    "allauth.account.middleware.AccountMiddleware",

]

# new29
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Secure cookies  new29
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True



ROOT_URLCONF = "socyfie_application.urls"
# LOGIN_URL = 'only_card:login_view'
LOGIN_REDIRECT_URL = 'service_auth.only_card:login_view'
#LOGOUT_REDIRECT_URL = "/"


CRISPY_TEMPLATE_PACK = 'bootstrap5'

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            os.path.join(BASE_DIR, "templates/base"),
            os.path.join(BASE_DIR, "templates/authentication"),
            os.path.join(BASE_DIR, "templates/nmkCoin"),
            os.path.join(BASE_DIR, "templates/landings"),
            os.path.join(BASE_DIR, "templates/group"),
            os.path.join(BASE_DIR, "templates/nmkChain"),
            os.path.join(BASE_DIR, "templates/notions"),
            os.path.join(BASE_DIR, "templates/user_profile"),
            os.path.join(BASE_DIR, "templates/only_message"),
            

            ],
        #'DIRS': [os.path.join(BASE_DIR, 'templates')],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                'django.template.context_processors.request',
            ],
        },
    },
]


COMPRESSED_MEDIA_STORAGE = {
    'storage': 'nmk.service_auth.storage.CompressedMediaStorage',
    'options': {
        'image_quality': 65,
        'video_crf': 28,
        'max_image_dimension': 1920,
        'audio_bitrate': '128k',
    },
}

MEDIA_URL = 'nmk/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'your_app.tasks': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    },
}


# # Celery settings notion deletion
# CELERY_BROKER_URL = 'redis://localhost:6379/0'  # Adjust based on your Redis setup
# CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'  # Optional: only needed if you need task results
# CELERY_ACCEPT_CONTENT = ['json']
# CELERY_TASK_SERIALIZER = 'json'
# CELERY_RESULT_SERIALIZER = 'json'
# CELERY_TIMEZONE = 'UTC'  # Adjust to your timezone


# Celery Configuration Options
CELERY_BROKER_URL = 'redis://localhost:6379/0'  # Redis is the broker for task queue
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'  # Optional: Used to store task results
CELERY_ACCEPT_CONTENT = ['json']  # Specifies allowed content types
CELERY_TASK_SERIALIZER = 'json'   # Serialize task messages as JSON
CELERY_RESULT_SERIALIZER = 'json'  # Serialize result data as JSON
CELERY_TIMEZONE = 'UTC'  # Set timezone, adjust according to your project requirements

# Retry broker connection during startup (to retain behavior in Celery 6.x+)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Celery task time limits (Optional - can add to avoid long-running tasks)
# CELERY_TASK_TIME_LIMIT = 300  # Task timeout in seconds
# CELERY_TASK_SOFT_TIME_LIMIT = 150  # Warning before task timeout

# Other optional Celery settings can be added here


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

# *
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-enqdbn^j&gt@ei5+q&#q+t8k4rhyle1j&$c!y%t7&z7e#)_k!h"
#ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY') or '<your_generated_encryption_key>'
ENCRYPTION_KEY = 't77yaXGqyj4S82d8G1N1Svj2TmMEB_YSGlbz7lW4284='

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
# DEBUG = os.getenv("DEBUG", "False") == "True"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "database_setup/db.sqlite3",
    }
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",},
]


#AUTH_USER_MODEL = 'only_card.CustomUserModel'


# Session settings
SESSION_ENGINE = 'django.contrib.sessions.backends.db'  # Or any other session backend you are using
SESSION_COOKIE_NAME = 'sessionid'
SESSION_COOKIE_AGE = 36000  #seconds
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
#SESSION_SAVE_EVERY_REQUEST = True
#SESSION_COOKIE_SECURE = True  # Use HTTPS for session cookies (set to True in production)
SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript from accessing the session cookie



EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
EMAIL_HOST_USER = 'nmkfinancialservices@gmail.com'
# EMAIL_HOST_PASSWORD = 'zakh htez cvyq pgmr' #yadavvaibhav
EMAIL_HOST_PASSWORD = 'qbms zhou gdpm ludo' #nmkfinincial
DEFAULT_FROM_EMAIL = 'no-reply@socyfie.com'  # Optional, sets the default sender address for emails



# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = "/static/"

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

#STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),
]


AUTHENTICATION_BACKENDS = [
    #'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
    #'social_core.backends.google.GoogleOAuth2',
]


SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = '57767563513-oieitul20quq9550mnhgeeqhom940rgm.apps.googleusercontent.com'
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = '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'