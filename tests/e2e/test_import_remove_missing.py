from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from server.models import db, Student

IMPORT_URL = 'http://localhost:5000/offerings/1234567/exams/midterm1/students/import/'


def _ask_to_remove_missing_students(driver):
    driver.get(IMPORT_URL)
    driver.find_element(By.CSS_SELECTOR, 'a[href="#canvas-panel"]').click()
    panel = driver.find_element(By.ID, 'canvas-panel')
    Select(panel.find_element(By.CSS_SELECTOR, 'select.missing-students')).select_by_value('delete')
    panel.find_element(By.CSS_SELECTOR, 'input[type=submit]').click()
    return WebDriverWait(driver, 5).until(EC.alert_is_present())


def test_removing_students_not_in_the_roster_is_confirmed(get_authed_driver, seeded_db):
    # a student who has left the course: the mock Canvas roster does not list them
    db.session.add(Student(exam_id=1, canvas_id='999999', name='Dropped Student', email='dropped@berkeley.edu',
                           wants=set(), avoids=set(), room_wants=set(), room_avoids=set()))
    db.session.commit()
    driver = get_authed_driver("123456")

    alert = _ask_to_remove_missing_students(driver)
    assert 'Remove every student of this exam who is not in this import' in alert.text
    alert.dismiss()
    assert driver.current_url == IMPORT_URL
    db.session.commit()  # end the test's transaction to see the server's writes
    assert Student.query.filter_by(exam_id=1, canvas_id='999999').count() == 1

    _ask_to_remove_missing_students(driver).accept()
    WebDriverWait(driver, 10).until(lambda d: d.current_url.endswith('/students/'))
    assert 'Removed students not in the import: Dropped Student' in driver.find_element(By.TAG_NAME, 'body').text
    db.session.commit()
    assert Student.query.filter_by(exam_id=1, canvas_id='999999').count() == 0
    assert Student.query.filter_by(exam_id=1).count() == 3
