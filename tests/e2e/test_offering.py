from selenium.webdriver.common.by import By


def test_user_can_see_offerings(get_authed_driver, seeded_db):
    driver = get_authed_driver("123456")
    first_offering_btn = driver.find_element(By.CSS_SELECTOR, ".mdl-list__item-primary-content")
    assert first_offering_btn is not None
