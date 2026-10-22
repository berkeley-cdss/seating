from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

EMAIL_URL = 'http://localhost:5000/offerings/1234567/exams/midterm1/students/email/'


def test_preview_shows_the_email_the_student_would_get(get_authed_driver, seeded_db):
    driver = get_authed_driver("123456")
    driver.get(EMAIL_URL)
    driver.find_element(By.ID, 'preview-button').click()
    WebDriverWait(driver, 10).until(lambda d: d.find_element(By.ID, 'preview').is_displayed())
    assert driver.find_element(By.ID, 'preview-subject').text == 'Your Exam Seating Assignment for Midterm 1'
    driver.switch_to.frame(driver.find_element(By.ID, 'preview-html'))
    email = driver.find_element(By.TAG_NAME, 'body').text
    assert 'Room: Soda 999' in email and 'Seat: A1' in email
    assert driver.find_element(By.TAG_NAME, 'a').get_attribute('href').endswith('/seats/1/')
    driver.switch_to.default_content()

    # a typo in a variable is pointed out, rather than previewed
    driver.execute_script("document.getElementById('body').value += ' {{ROOOM}}'")
    driver.find_element(By.ID, 'preview-button').click()
    WebDriverWait(driver, 10).until(lambda d: d.find_element(By.ID, 'preview-error').text)
    assert driver.find_element(By.ID, 'preview-error').text == \
        '{{ROOOM}} is not a variable; the variables are listed below the email.'
    assert not driver.find_element(By.ID, 'preview').is_displayed()
