from flask import request, session


def remember_page_for_after_login():
    """
    Sends the user back to this page once they've signed in, if it's a page: the sign-in comes back
    with a GET, so a post (e.g. pressing Delete once the session has expired) would end on a 405.
    Those land on the home page instead.
    """
    if request.method == 'GET':
        session['after_login'] = request.url
