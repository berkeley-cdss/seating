from flask import Flask, redirect
import logging
import flask.ctx
from werkzeug.exceptions import HTTPException
from canvasapi.exceptions import InvalidAccessToken

from server.typings.enum import AppEnvironment
from server.typings.exception import EnvironmentalVariableMissingError


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


if __name__ != '__main__':
    # Only configure logging if running on a WSGI server, like gunicorn on Heroku
    app.logger.addHandler(logging.StreamHandler())
    app.logger.setLevel(logging.INFO)


from config import ConfigBase, ProductionConfig, StagingConfig, DevelopmentConfig, TestingConfig  # noqa
# FLASK_ENV defaults to development when not explicitly set
env_value = ConfigBase.getenv('FLASK_ENV', AppEnvironment.DEVELOPMENT.value).lower()

config_mapping = {
    AppEnvironment.PRODUCTION.value: ProductionConfig,
    AppEnvironment.TESTING.value: TestingConfig,
    AppEnvironment.STAGING.value: StagingConfig,
    AppEnvironment.DEVELOPMENT.value: DevelopmentConfig,
}

selected_config_class = config_mapping.get(env_value, None)

if selected_config_class:
    app.config.from_object(selected_config_class())
else:
    raise EnvironmentalVariableMissingError('FLASK_ENV')

# Sentry is only enabled in staging and production. Development and testing
# environments never report to Sentry.
SENTRY_ENABLED_ENVIRONMENTS = {
    AppEnvironment.STAGING.value,
    AppEnvironment.PRODUCTION.value,
}

if env_value in SENTRY_ENABLED_ENVIRONMENTS:
    import sentry_sdk  # noqa

    sentry_sdk.init(
        dsn="https://bb1482ed49f0807ee6a49accafe927f9@o4506322522734592.ingest.sentry.io/4506322540953600",
        # Tag every event with the app environment so staging and production
        # issues can be told apart in Sentry.
        environment=env_value,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        traces_sample_rate=1.0,
        # Set profiles_sample_rate to 1.0 to profile 100%
        # of sampled transactions.
        # We recommend adjusting this value in production.
        profiles_sample_rate=1.0,
    )


@app.errorhandler(InvalidAccessToken)
def handle_invalid_access_token(e):
    """
    Redirects to login page if the Canvas access token is invalid or expired.
    """
    return redirect('/login')


# Defense in depth should a script ever get injected again: pages load scripts, styles, fonts and
# images only from this app, and fetch() only from this app, so an injected script cannot fetch()
# or load an image to hand data to another site.
# Inline <script> blocks and onclick= handlers are still allowed, as the templates use them
# throughout; dropping 'unsafe-inline' from script-src needs those moved into static/js first.
# There is no form-action: browsers apply it to the redirects after a form is posted, and a post
# made once the Canvas token has expired is redirected to Canvas to log in again.
CONTENT_SECURITY_POLICY = '; '.join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self'",
    # Bootstrap draws its checkboxes, selects and close buttons with data: SVGs
    "img-src 'self' data:",
    "connect-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
])


@app.after_request
def set_security_headers(response):
    response.headers.setdefault('Content-Security-Policy', CONTENT_SECURITY_POLICY)
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    return response


app.jinja_env.filters.update(
    min=min,
    max=max,
)


# These must be done after `app`` is created as they depend on `app`

# prepare server cache
import server.cache  # noqa

# prepares all auth clients
import server.services.auth  # noqa

# prepares mock canvas db
import server.services.canvas.fake_data  # noqa

# registers controller converters
from server.controllers import ExamConverter, OfferingConverter, StudentConverter  # noqa
app.url_map.converters['exam_student'] = StudentConverter
app.url_map.converters['exam'] = ExamConverter
app.url_map.converters['offering'] = OfferingConverter

# registers base controllers (depends on converters, so must be done after)
import server.views  # noqa

# registers blueprint controllers
from server.controllers import auth_module, dev_login_module, health_module  # noqa
app.register_blueprint(dev_login_module)
app.register_blueprint(auth_module)
app.register_blueprint(health_module)

# registers flask cli commands
import cli  # noqa
