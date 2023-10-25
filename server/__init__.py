import os

from flask import Flask, redirect
import flask.ctx
from werkzeug.exceptions import HTTPException
from canvasapi.exceptions import InvalidAccessToken


class UrlRequestContext(flask.ctx.RequestContext):
    def match_request(self):
        pass

    def push(self):
        super().push()
        try:
            url_rule, self.request.view_args = \
                self.url_adapter.match(return_rule=True)
            self.request.url_rule = url_rule
        except HTTPException as e:
            self.request.routing_exception = e


class App(Flask):
    def request_context(self, environ):
        return UrlRequestContext(self, environ)


app = App(__name__)


# when canvas token expires or is invalid, redirect to login page
@app.errorhandler(InvalidAccessToken)
def handle_invalid_access_token(e):
    return redirect('/login')


from config import ProductionConfig, DevelopmentConfig, TestingConfig  # noqa

if os.getenv('FLASK_ENV').lower() == 'production':
    app.config.from_object(ProductionConfig())
elif os.getenv('FLASK_ENV').lower() == 'testing':
    app.config.from_object(TestingConfig())
elif os.getenv('FLASK_ENV').lower() == 'development':
    app.config.from_object(DevelopmentConfig())
else:
    raise ValueError('FLASK_ENV not set to any of the valid values: production, testing, or development')

app.jinja_env.filters.update(
    min=min,
    max=max,
)


import server.utils.auth  # noqa
import server.models  # noqa
import server.views  # noqa
import tests.conftest  # noqa
