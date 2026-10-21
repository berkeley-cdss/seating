from selenium.webdriver.common.by import By

from tests.a11y.utils import load_axe_scripts
import tests.a11y.utils as axe_utils

EMAIL_URL = 'http://localhost:5000/offerings/1234567/exams/midterm1/students/email/'


def test_a11y_test_email_section_contrast(seeded_db, get_authed_driver):
    """
    The "Send a test" section of the email page has enough color contrast. The shared axe config
    turns the color-contrast rule off, so run it here, on this section only.
    """
    driver = get_authed_driver("123456")
    driver.get(EMAIL_URL)
    section = driver.find_element(By.CSS_SELECTOR, '.test-email')
    # axe only judges the contrast of text that is on screen
    driver.execute_script('arguments[0].scrollIntoView({block: "center"})', section)
    if axe_utils.AXE_SCRIPT_CONTENT is None:
        load_axe_scripts()
    driver.execute_script(axe_utils.AXE_SCRIPT_CONTENT)
    violations = driver.execute_async_script("""
        const done = arguments[0];
        axe.run({include: ['.test-email']}, {runOnly: ['color-contrast']}).then(r => done(r.violations));
    """)
    assert violations == [], [node['html'] for violation in violations for node in violation['nodes']]
