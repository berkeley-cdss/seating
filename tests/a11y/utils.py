def run_axe(driver):
    with open('tests/a11y/axe.min.js', 'r') as f:
        axe_script = f.read()
        driver.execute_script(axe_script)
        return driver.execute_script('return axe.run();')


def print_violations(report):
    violations = report.get('violations', [])
    if len(violations) == 0:
        print("No violations found!")
        return
    for i, violation in enumerate(violations, start=1):
        print(f"Violation {i}:")
        print(f"  ID: {violation['id']}")
        print(f"  Description: {violation['description']}")
        print(f"  Impact: {violation['impact']}")
        for node in violation['nodes']:
            print(f"  - Selector: {node['target']}")
            print(f"    HTML: {node['html']}")
            if len(node['any']) > 0:
                print(f"    Remediation: {node['any'][0]['message']}")


def save_report(title, report):
    from pathlib import Path
    Path("axe").mkdir(parents=True, exist_ok=True)
    with open(f"axe/{title}.json", "w") as f:
        import json
        json.dump(report, f, indent=2)


def assert_no_violations(report, print_if_violations=True):
    if len(report.get('violations', [])) > 0 and print_if_violations:
        print_violations(report)
    assert len(report['violations']) == 0
