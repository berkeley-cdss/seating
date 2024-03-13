from flask import jsonify, current_app

from server.controllers import health_module


@health_module.route('/')
def check():
    return jsonify(status="UP"), 200


@health_module.route('/db')
def check_db():
    from server.models import db
    try:
        db.session.execute("SELECT 1")
        return jsonify(status="UP"), 200
    except Exception as e:
        return jsonify(status="DOWN", error=str(e)), 500


@health_module.route('/log')
def check_logging():
    current_app.logger.debug("Debug logging is working")
    current_app.logger.info("Info logging is working")
    current_app.logger.warning("Warning logging is working")
    current_app.logger.error("Error logging is working")
    return jsonify(status="SEE LOGS"), 200
