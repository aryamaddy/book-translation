import os

def auth_status(request):
    """
    Exposes OAuth availability to all templates.
    """
    google_client_id = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
    return {
        'google_auth_enabled': bool(google_client_id),
    }
