import click
import os


@click.command('test')
def run_all():
    click.echo('Running all tests...')
    os.system("""pytest tests --cov=server --cov-report=term-missing --junitxml=reports/pytest.xml --cov-report=term-missing:skip-covered --cov-report=html:reports/coverage --cov-config=tests/.coveragerc""")  # noqa: E501
    # the above uses command line to run tests (instead of pytest module) so python import lines are counted as covered
    # see https://stackoverflow.com/questions/70674067
    # pytest.main(['tests', '--cov=server', '--cov-report=term-missing', '--junitxml=reports/pytest.xml',
    #             '--cov-report=term-missing:skip-covered', '--cov-report=html:reports/coverage',
    #              ])


@click.command('unit')
def run_unit():
    click.echo('Running unit tests...')
    os.system("""pytest tests/unit --cov=server --cov-report=term-missing --junitxml=reports/pytest-unit.xml --cov-report=term-missing:skip-covered --cov-report=html:reports/coverage-unit --cov-config=tests/.coveragerc""")  # noqa: E501


@click.command('e2e')
def run_e2e():
    click.echo('Running end-to-end tests...')

    os.system("""pytest tests/e2e --cov=server --cov-report=term-missing --junitxml=reports/pytest-e2e.xml --cov-report=term-missing:skip-covered --cov-report=html:reports/coverage-e2e --cov-config=tests/.coveragerc""")  # noqa: E501


@click.command('a11y')
def run_a11y():
    click.echo('Running accessibility tests...')
    os.system("""pytest tests/a11y --cov=server --cov-report=term-missing --junitxml=reports/pytest-a11y.xml --cov-report=term-missing:skip-covered --cov-report=html:reports/coverage-a11y --cov-config=tests/.coveragerc""")  # noqa: E501


@click.command('audit')
def run_audit():
    click.echo('Checking for broken dependencies...')
    os.system('pip check')
    click.echo('Checking for outdated dependencies...')
    os.system('pip list --outdated')
    click.echo('Auditing with pip-audit...')
    os.system('pip-audit')


@click.command('lint')
def run_lint():
    click.echo('Running flake8 linter...')
    os.system('flake8 server tests')
