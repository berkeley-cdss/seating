from selenium.webdriver.common.by import By


def test_ta_can_see_offerings(get_authed_driver, seeded_db):
    driver = get_authed_driver("123456")
    first_offering_btn = driver.find_element(By.CSS_SELECTOR, ".item-link")
    assert "Introduction to Software Engineering" in first_offering_btn.text


def test_ta_can_see_exam(get_authed_driver, seeded_db):
    driver = get_authed_driver("123456")
    first_offering_btn = driver.find_element(By.CSS_SELECTOR, ".item-link")
    first_offering_btn.click()
    exam_btn = driver.find_element(By.CSS_SELECTOR, ".item-link")
    assert "Midterm 1" in exam_btn.text
