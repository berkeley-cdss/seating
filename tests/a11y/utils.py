import json
import re
from pathlib import Path

AXE_SCRIPT_PATH = Path(__file__).parent / 'axe.min.js'
AXE_SCRIPT_CONTENT = None

# axe-core tags, see https://github.com/dequelabs/axe-core/blob/develop/doc/API.md#axe-core-tags
# Berkeley requires WCAG 2.1 AA (https://dap.berkeley.edu/), so every page must pass these.
REQUIRED_A11Y_STANDARDS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']
# WCAG 2.2 AA is the current standard, so every page must pass these too.
COMPLETE_A11Y_STANDARDS = ['wcag22aa', 'best-practice', 'section508']

# axe-core rules that do not apply. It should be rare to add to this list.
# See https://github.com/dequelabs/axe-core/blob/develop/doc/rule-descriptions.md
SKIPPED_RULES = []
# Elements that every rule skips, e.g. <div data-a11y-errors="true">. This is a last resort:
# match the smallest part of the page you can, and say why in the template.
EXCLUDED_ELEMENTS = ['[data-a11y-errors="true"]']

REPORT_DIR = Path('axe')


def load_axe_script():
    global AXE_SCRIPT_CONTENT
    if AXE_SCRIPT_CONTENT is None:
        AXE_SCRIPT_CONTENT = AXE_SCRIPT_PATH.read_text()
    return AXE_SCRIPT_CONTENT


def run_axe(driver, standards=REQUIRED_A11Y_STANDARDS):
    """Runs axe on the page the driver is on and returns its report."""
    driver.execute_script(load_axe_script())
    report = driver.execute_async_script("""
        const [tags, exclude, skipped, done] = arguments;
        const rules = Object.fromEntries(skipped.map(id => [id, {enabled: false}]));
        axe.run({include: [document], exclude: exclude},
                {runOnly: {type: 'tag', values: tags}, rules: rules})
            .then(done, error => done({error: String(error)}));
    """, standards, EXCLUDED_ELEMENTS, SKIPPED_RULES)
    assert 'error' not in report, report.get('error')
    return report


def format_violations(report):
    lines = []
    for violation in report.get('violations', []):
        lines.append(f"{violation['id']} ({violation['impact']}): {violation['help']}")
        lines.append(f"  {violation['helpUrl']}")
        for node in violation['nodes']:
            lines.append(f"  - {' '.join(map(str, node['target']))}")
            lines.append(f"    {node['html']}")
            for summary in node.get('failureSummary', '').splitlines():
                lines.append(f"    {summary}")
    return '\n'.join(lines)


def save_report(title, report):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORT_DIR / f"{slugify(title)}.json", 'w') as f:
        json.dump(report, f, indent=2)


def slugify(text):
    return re.sub(r'[^\w.-]+', '-', text).strip('-')


def assert_no_violations(report):
    assert not report.get('violations'), '\n' + format_violations(report)
