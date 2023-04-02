import os

from dotenv import load_dotenv
from flask import url_for

from app import create_app

load_dotenv()

app = create_app()


def test_login_with_client_id(client):
    response = client.post('/api/auth/login',
                           json={'client_id': os.environ.get('CLIENT_ID'),
                                 'client_secret': os.environ.get('CLIENT_SECRET')})
    assert 'access_token' in response.get_json()
    assert 'refresh_token' in response.get_json()
