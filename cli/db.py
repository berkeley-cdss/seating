import click

from server.models import db, Exam
from server import app
from tests.fixtures import seed_db as _seed_db


@app.cli.command('initdb')
def init_db():
    """
    Initializes the database
    """
    click.echo('Creating database...')
    db.create_all()
    db.session.commit()


@app.cli.command('dropdb')
def drop_db():
    """
    Drops all tables from the database
    """
    doit = click.confirm('Are you sure you want to delete all data?')
    if doit:
        click.echo('Dropping database...')
        db.drop_all()


@app.cli.command('seeddb')
def seed_db():
    """
    Seeds the database with data
    There is no need to seed even in development, since the database is
    dynamically populated when app launches, see stub.py
    """
    click.echo('Seeding database...')
    _seed_db()


@app.cli.command('resetdb')
@click.pass_context
def reset_db(ctx):
    "Drops, initializes, then seeds tables with data"
    ctx.invoke(drop_db)
    ctx.invoke(init_db)
    ctx.invoke(seed_db)


@app.cli.command('cleanroomprefs')
@click.option('--dry-run', is_flag=True, help='Report what would change without saving it.')
def clean_room_prefs(dry_run):
    """
    Removes ids of deleted rooms from every student's room wants/avoids
    """
    total = 0
    for exam in Exam.query.all():
        changed = exam.remove_unknown_room_preferences()
        if changed:
            click.echo(f'{exam.offering_canvas_id}/{exam.name}: {changed} students')
            total += changed
    if dry_run:
        db.session.rollback()
        click.echo(f'Dry run: would update {total} students.')
    else:
        db.session.commit()
        click.echo(f'Updated {total} students.')
