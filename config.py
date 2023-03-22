import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URI')


environments = {
    'development': DevelopmentConfig
}

env_setting = os.environ.get('FLASK_ENV', 'production')
environment = environments.get(env_setting)