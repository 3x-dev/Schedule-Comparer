import os

class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv('Database_URL', 'postgres://default:YCtJ8bjhv7za@ep-calm-credit-a4qi4i6r-pooler.us-east-1.aws.neon.tech:5432/verceldb?sslmode=require')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.urandom(24)