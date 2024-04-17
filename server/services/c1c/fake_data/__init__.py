import json

FAKE_PHOTO_DICT = None

if not FAKE_PHOTO_DICT:
    with open('server/services/c1c/fake_data/photos.json', 'rb') as f:
        FAKE_PHOTO_DICT = json.load(f)


def get_fake_photo(student_canvas_id):
    try:
        with open(f"server/services/c1c/fake_data/photos/{FAKE_PHOTO_DICT[student_canvas_id]}",
                  'rb') as f:
            return f.read()
    except Exception as e:
        print(e)
        return None
