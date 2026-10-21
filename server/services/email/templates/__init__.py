from server.typings.enum import EmailTemplate
import os
import json
import re

from markupsafe import escape


class EmailContent:
    def __init__(self, subject: str, body: str, body_html: bool):
        self.subject = subject
        self.body = body
        self.body_html = body_html

    def apply_substitutions(self, subject_substitutions: dict[str, str], body_substitutions: dict[str, str]):
        if subject_substitutions:
            self.subject = make_substitutions(self.subject, subject_substitutions)
        if body_substitutions:
            self.body = make_substitutions(self.body, body_substitutions, html=self.body_html)

    def __repr__(self) -> str:
        return f'EmailContent(subject={self.subject}, body={self.body}, body_type={self.body_html})'


def get_email(
        template: EmailTemplate,
        subject_substitutions: dict[str, str] = None,
        body_substitutions: dict[str, str] = None
) -> EmailContent:
    # template.value is the file name for email metadata (json)
    # let us read it that first. The file sits in the same path as this file.
    email_metadata = None
    with open(os.path.join(os.path.dirname(__file__), template.value + ".json")) as f:
        email_metadata = json.load(f)
    subject = email_metadata['subject']
    body_html = email_metadata['body_html']
    body_path = os.path.join(os.path.dirname(__file__), email_metadata['body_path'])
    body = None
    with open(body_path) as f:
        body = f.read()
    content = EmailContent(subject, body, re.match('[Tt]rue', body_html) is not None)
    content.apply_substitutions(subject_substitutions, body_substitutions)
    return content


def make_substitutions(text: str, substitutions: dict[str, str], html: bool = False) -> str:
    """
    Fill in the {{KEY}} placeholders of `text`. With `html`, the values are HTML-escaped, since
    names and other values come from imports and staff input; plain text gets them as they are.
    """
    for key, value in substitutions.items():
        value = str(escape(value)) if html else str(value)
        # a function as the replacement takes the value literally: as a string, re.sub would read
        # backslashes in it (a name like "Jo\hn") as escapes and fail
        text = re.sub(r'\{\{\s*' + re.escape(key) + r'\s*\}\}', lambda _: value, text)
    return text
