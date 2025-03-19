"""
Django settings for nmk project.

Generated by 'django-admin startproject' using Django 4.2.11.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""
'''
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


SITE_ID = 2

APPEND_SLASH = True


# # Read the encryption key from environment variable
# ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY')

# if not ENCRYPTION_KEY:
#     raise ValueError("No ENCRYPTION_KEY set for Flask application. Did you forget to set it?")

# ..-----...-------...


# # new
env = environ.Env()
env_path = os.path.join(BASE_DIR, '.env')
environ.Env.read_env(env_path)  # Reads the .env file


# # Read the encryption key from the environment
ENCRYPTION_KEY = env('ENCRYPTION_KEY')
SECRET_KEY = env('SECRET_KEY')
#ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])
ALLOWED_HOSTS = ["socyfie.com","www.socyfie.com","ec2-13-235-125-150.ap-south-1.compute.amazonaws.com"]

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
            'hosts': [('redis://:090399Akash$@13.235.125.150:6379/0')],
        },
        'ROUTING': 'service_auth.only_message_channels.routing.channel_routing',
    }
}


CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'redis://:090399Akash@$13.235.125.150:6379/1',  # For Redis
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
SECURE_SSL_REDIRECT = False
USE_X_FORWARDED_HOST = True
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
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Secure cookies  new29
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"   #new vanuralibity protection

SECURE_CONTENT_TYPE_NOSNIFF = True   #new vanuralibity protection




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
        # 'video_crf': 28,
        'max_image_dimension': 1920,
        'audio_bitrate': '128k',
    },
}


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


# Celery Configuration Options
CELERY_BROKER_URL = 'redis://:090399Akash$@13.235.125.150:6379/0'  # Redis is the broker for task queue
CELERY_RESULT_BACKEND = 'redis://:090399Akash$@13.235.125.150:6379/0'  # Optional: Used to store task results
CELERY_ACCEPT_CONTENT = ['json']  # Specifies allowed content types
CELERY_TASK_SERIALIZER = 'json'   # Serialize task messages as JSON
CELERY_RESULT_SERIALIZER = 'json'  # Serialize result data as JSON
CELERY_TIMEZONE = 'UTC'  # Set timezone, adjust according to your project requirements

# Retry broker connection during startup (to retain behavior in Celery 6.x+)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
# *
# SECURITY WARNING: keep the secret key used in production secret!
# SECURITY WARNING: don't run with debug turned on in production!
# DEBUG = False
DEBUG = env.bool('DEBUG', default=False)
# DEBUG = os.getenv("DEBUG", "False") == "True"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": "socyfiedev",
        "USER": "testadmin",
        "PASSWORD": "090399Akash$",
        "HOST": "13.235.125.150",
        "PORT": "5432",
    }
}
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": "database_setup/db.sqlite3",
#     }
# }
# DATABASE_URL = env('DATABASE_URL', default='')


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
# EMAIL_HOST_USER = 'nmkfinancialservices@gmail.com'
EMAIL_HOST_USER = env('EMAIL_HOST_USER')
# EMAIL_HOST_PASSWORD = 'zakh htez cvyq pgmr' #yadavvaibhav
# EMAIL_HOST_PASSWORD = 'qbms zhou gdpm ludo' #nmkfinincial
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
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
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),
]

#MEDIA_URL = 'nmk/media/'
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CSRF_TRUSTED_ORIGINS = [
    'https://localhost:8000', 
    'https://socyfie.com', 
    'https://www.socyfie.com',
    'https://socyfiedev.ch6weeg28qnq.ap-south-1.rds.amazonaws.com'
    ]


AUTHENTICATION_BACKENDS = [
    #'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
    #'social_core.backends.google.GoogleOAuth2',
]


SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = env('SOCIAL_AUTH_GOOGLE_OAUTH2_KEY')
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = env('SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET')

'''







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


SITE_ID = 2

APPEND_SLASH = True


# # Read the encryption key from environment variable
# ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY')

# if not ENCRYPTION_KEY:
#     raise ValueError("No ENCRYPTION_KEY set for Flask application. Did you forget to set it?")

# ..-----...-------...


# # new
env = environ.Env()
env_path = os.path.join(BASE_DIR, '.env')
environ.Env.read_env(env_path)  # Reads the .env file


# # Read the encryption key from the environment
ENCRYPTION_KEY = env('ENCRYPTION_KEY')
SECRET_KEY = env('SECRET_KEY')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])

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
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True


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
SECURE_HSTS_SECONDS = 31536000
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
        # 'video_crf': 28,
        'max_image_dimension': 1920,
        'audio_bitrate': '128k',
    },
}



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


# Celery Configuration Options
CELERY_BROKER_URL = 'redis://localhost:6379/0'  # Redis is the broker for task queue
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'  # Optional: Used to store task results
CELERY_ACCEPT_CONTENT = ['json']  # Specifies allowed content types
CELERY_TASK_SERIALIZER = 'json'   # Serialize task messages as JSON
CELERY_RESULT_SERIALIZER = 'json'  # Serialize result data as JSON
CELERY_TIMEZONE = 'UTC'  # Set timezone, adjust according to your project requirements

# Retry broker connection during startup (to retain behavior in Celery 6.x+)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
# *
# SECURITY WARNING: keep the secret key used in production secret!
# SECURITY WARNING: don't run with debug turned on in production!
# DEBUG = False
DEBUG = env.bool('DEBUG', default=False)
# DEBUG = os.getenv("DEBUG", "False") == "True"

# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql_psycopg2",
#         "NAME": "socyfiedev",
#         "USER": "postgres",
#         "PASSWORD": env('DATABASE_HOST_PASSWORD'),
#         "HOST": "localhost",
#         "PORT": "5432",
#     }
# }
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "database_setup/db.sqlite3",
    }
}
DATABASE_URL = env('DATABASE_URL', default='')


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
# EMAIL_HOST_USER = 'nmkfinancialservices@gmail.com'
EMAIL_HOST_USER = env('EMAIL_HOST_USER')
# EMAIL_HOST_PASSWORD = 'zakh htez cvyq pgmr' #yadavvaibhav
# EMAIL_HOST_PASSWORD = 'qbms zhou gdpm ludo' #nmkfinincial
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
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
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),
]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CSRF_TRUSTED_ORIGINS = [
    'https://localhost:8000', 
    'https://socyfie.com', 
    'https://www.socyfie.com'
    ]


AUTHENTICATION_BACKENDS = [
    #'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
    #'social_core.backends.google.GoogleOAuth2',
]


SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = env('SOCIAL_AUTH_GOOGLE_OAUTH2_KEY')
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = env('SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET')

