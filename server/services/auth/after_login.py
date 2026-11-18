from flask import flash, request, session

NOT_DONE = "You were signed out, so that wasn't done. Sign in and try again."


def remember_page_for_after_login():
    """
    Sends the user back to this page once they've signed in, if it's a page. The sign-in comes back
    with a GET, so a post (e.g. pressing Delete once the session has expired) can't be redone that
    way, and would end on a 405 for a POST-only url: it lands on the home page instead, saying it
    wasn't done.
    """
    if request.method == 'GET':
        session['after_login'] = request.url
    elif request.method not in ('HEAD', 'OPTIONS'):
        # not a page from some earlier signed-out visit either
        session.pop('after_login', None)
        flash(NOT_DONE, 'warning')
