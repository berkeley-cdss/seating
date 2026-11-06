from flask import current_app
from flask_caching import Cache

# set up for each app by create_app
cache_store = Cache()


def cache_key_photo(canvas_id: str):
    return f'student_photo_{canvas_id}'


def cache_life_photo():
    return int(current_app.config.get('C1C_PHOTO_CACHE_LIFE'))
