from server.typings.enum import AppEnvironment


def commands(app):
    """The flask commands create_app adds: the database ones, and in development and testing the QA ones."""
    import cli.db as db
    result = [db.init_db, db.drop_db, db.seed_db, db.reset_db, db.clean_room_prefs]
    if app.config['FLASK_ENV'] in (AppEnvironment.DEVELOPMENT.value, AppEnvironment.TESTING.value):
        import cli.qa as qa
        result += [qa.run_all, qa.run_unit, qa.run_e2e, qa.run_a11y, qa.run_audit, qa.run_lint]
    return result
