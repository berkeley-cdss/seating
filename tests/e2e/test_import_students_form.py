from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from server.models import db, Student

IMPORT_URL = 'http://localhost:5000/offerings/1234567/exams/midterm1/students/import/'
ROWS = 'canvas id\temail\tname\n777777\tnew@berkeley.edu\tNew Student\n'


def _submit(driver):
    driver.find_element(By.CSS_SELECTOR, '#import-students input[type=submit]').click()
    return driver.find_element(By.ID, 'import-source-error').text


def test_import_form_takes_exactly_one_source(get_authed_driver, seeded_db):
    driver = get_authed_driver("123456")
    driver.get(IMPORT_URL)

    assert _submit(driver) == 'Choose a file, paste rows or link a Google Sheet.'
    assert driver.current_url == IMPORT_URL

    # as if pasted: typing a tab would move the focus out of the box instead
    driver.execute_script("document.getElementById('import_text').value = arguments[0]", ROWS)
    driver.find_element(By.ID, 'import_sheet_url').send_keys('https://docs.google.com/spreadsheets/d/abc/edit')
    assert _submit(driver) == 'Choose only one: a file, pasted rows or a Google Sheet link.'
    assert driver.current_url == IMPORT_URL

    # pasted rows alone, tab separated as copied out of a spreadsheet, are imported
    driver.find_element(By.ID, 'import_sheet_url').clear()
    driver.find_element(By.CSS_SELECTOR, '#import-students input[type=submit]').click()
    WebDriverWait(driver, 10).until(lambda d: d.current_url.endswith('/students/'))
    assert 'Import done. 1 new students' in driver.find_element(By.TAG_NAME, 'body').text
    db.session.commit()  # end the test's transaction to see the server's writes
    assert Student.query.filter_by(exam_id=1, canvas_id='777777').count() == 1
