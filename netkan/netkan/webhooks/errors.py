from flask import Blueprint, current_app


errors = Blueprint('errors', __name__)  # pylint: disable=invalid-name


@errors.app_errorhandler(Exception)
def handle_error(exc):
    current_app.logger.error("Uncaught exception:", exc_info=exc)
    return '', 500
