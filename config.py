import os


class ConfigBase(object):
    FLASK_APP = "server"
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

    SQLALCHEMY_TRACK_MODIFICATIONS = False
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
    DOMAIN = os.getenv('DOMAIN')

    PHOTO_DIRECTORY = os.getenv('PHOTO_DIRECTORY')


class ProductionConfig(ConfigBase):
    DEBUG = False
    TESTING = False
    FLASK_ENV = 'production'
    SECRET_KEY = os.getenv('SECRET_KEY')
    MOCK_CANVAS = False

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return os.getenv('DATABASE_URL').replace('mysql://', 'mysql+pymysql://')


class DevelopmentConfig(ConfigBase):
    DEBUG = True
    TESTING = False
    FLASK_ENV = 'development'
    SECRET_KEY = 'development'

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return 'sqlite:///' + os.path.join(self.BASE_DIR, 'app.db')


class TestingConfig(ConfigBase):
    DEBUG = False
    TESTING = True
    FLASK_ENV = 'testing'
    SECRET_KEY = 'testing'
    MOCK_CANVAS = True

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return 'sqlite:///' + os.path.join(self.BASE_DIR, 'test.db')
