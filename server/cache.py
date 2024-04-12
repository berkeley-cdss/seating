from flask_caching import Cache
from server import app

cache_store = Cache(app, config={
    'CACHE_TYPE': 'FileSystemCache',
    'CACHE_DIR': '.cache',
    'CACHE_DEFAULT_TIMEOUT': 3600}
)


def cache_key_photo(canvas_id: str):
    return f'student_photo_{canvas_id}'


cache_life_photo = int(app.config.get('C1C_PHOTO_CACHE_LIFE'))
