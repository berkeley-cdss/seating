# Define the application directory
import os
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# environment
FLASK_ENV = os.getenv('FLASK_ENV', 'development')

# Secret key for signing cookies
SECRET_KEY = os.getenv('SECRET_KEY', 'development')

# Define the database
# We are working with SQLite for development, mysql for production
# [development should be changed to mysql in the future]
if FLASK_ENV == 'development':
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'app.db')
else:
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL').replace('mysql://', 'mysql+pymysql://')
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Configure timezone
LOCAL_TIMEZONE = os.getenv('TIMEZONE', 'US/Pacific')

# Coogle API setup
GOOGLE_OAUTH2_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_OAUTH2_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')

# Canvas API setup
CANVAS_SERVER_URL = os.getenv('CANVAS_SERVER_URL')
CANVAS_CLIENT_ID = os.getenv('CANVAS_CLIENT_ID')
CANVAS_CLIENT_SECRET = os.getenv('CANVAS_CLIENT_SECRET')
MOCK_CANVAS = os.getenv('MOCK_CANVAS', 'false').lower() == 'true'

# Email setup. Domain environment is for link in email.
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
DOMAIN = os.getenv('DOMAIN', 'https://seating.test.org')

PHOTO_DIRECTORY = os.getenv('PHOTO_DIRECTORY')
