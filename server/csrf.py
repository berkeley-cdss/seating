"""
CSRF protection for the whole app: every POST needs the session's CSRF token, so a link or form on
another site can't change data for a signed-in staff member. Routes that change data take only POST.
"""
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()
