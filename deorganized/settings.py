import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'

# Production
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',')


# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'django_celery_beat',
    
    # Local apps
    'users',
    'news',
    'events',
    'shows',
    'api',
    'posts',
    'merch',
    'payments',
    'messaging',
]

# Custom User Model
AUTH_USER_MODEL = 'users.User'

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # CORS should be at the top
   'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # For static files in production
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'deorganized.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'deorganized.wsgi.application'


# Database
# Default: SQLite for local development
# Production: Set DATABASE_URL environment variable for PostgreSQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Override with PostgreSQL if DATABASE_URL is set (for production)
if os.environ.get('DATABASE_URL'):
    import dj_database_url
    DATABASES['default'] = dj_database_url.config(
        default=os.environ.get('DATABASE_URL'),
        conn_max_age=600,
        ssl_require=True
    )



# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Whitenoise configuration for serving static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# Tell WhiteNoise to NOT handle media files - let Django serve them
WHITENOISE_AUTOREFRESH = True
WHITENOISE_USE_FINDERS = True  
WHITENOISE_ROOT = None  # Don't serve root directory
WHITENOISE_INDEX_FILE = False  # Don't serve index.html

# Media files (User uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS Settings - Allow all origins for development
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = [
    'payment-required',
    'payment-response',
]
CORS_ALLOW_HEADERS = [
    # defaults
    'accept', 'accept-encoding', 'authorization', 'content-type',
    'dnt', 'origin', 'user-agent', 'x-csrftoken', 'x-requested-with',
    # x402 custom headers
    'payment-signature', 'x-payment-token-type',
]

# Stacks Network Configuration
STACKS_NETWORK = os.environ.get('STACKS_NETWORK', 'mainnet')


# Security settings for production
if not DEBUG:
    # Railway-specific: Trust proxy headers for HTTPS detection
    # This MUST come before SECURE_SSL_REDIRECT to prevent infinite redirect loop
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    
    # Now it's safe to redirect to HTTPS
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
}

# JWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
}

# ---------------------------------------------------------------------------
# DCPE (Digital Content Processing Engine) Configuration
# ---------------------------------------------------------------------------
DCPE_BASE_URL = os.environ.get('DCPE_BASE_URL', '')
DCPE_API_KEY = os.environ.get('DCPE_API_KEY', '')

# Railway API (for set-mode / remove via GraphQL)
RAILWAY_API_TOKEN = os.environ.get('RAILWAY_API_TOKEN', '')
RAILWAY_PROJECT_ID = os.environ.get('RAILWAY_PROJECT_ID', '')
RAILWAY_SERVICE_ID = os.environ.get('RAILWAY_SERVICE_ID', '')
RAILWAY_ENV_ID = os.environ.get('RAILWAY_ENV_ID', '')

# Platform Configuration
PLATFORM_WALLET_ADDRESS = os.environ.get('PLATFORM_WALLET_ADDRESS', '')
# Celery Configuration
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Celery Beat Schedule
from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    'check-upcoming-shows-every-5-min': {
        'task': 'shows.tasks.check_upcoming_shows',
        'schedule': crontab(minute='*/5'),
    },
    'register-airing-episodes-every-minute': {
        'task': 'shows.tasks.register_airing_episodes',
        'schedule': crontab(minute='*'),
    },
    'auto-create-recurring-episodes-daily': {
        'task': 'shows.tasks.auto_create_recurring_episodes',
        'schedule': crontab(hour=0, minute=30),  # Run at 00:30 AM
    },
    'auto-cancel-unconfirmed-shows-every-5-min': {
        'task': 'shows.tasks.auto_cancel_unconfirmed_shows',
        'schedule': crontab(minute='*/5'),
    },
    'cleanup-old-notifications-daily': {
        'task': 'shows.tasks.cleanup_old_notifications',
        'schedule': crontab(hour=0, minute=0),
    },
}
