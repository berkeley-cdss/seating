"""
Assignment emails. Staff write plain text with {{VARIABLE}} placeholders (issue #140), and both parts
of the email are built from it: a plain-text part, and an HTML part from assignment_email.html in which
blank lines start paragraphs, links are clickable and {{SEAT_DETAILS_LIST}} is a list.

Staff text is only ever data: it is never rendered as a Jinja template, which would let whoever
writes the email run code on the server. The HTML template gets it in pieces, and escapes them.
"""
from server.typings.enum import EmailTemplate
import os
import json
import re

from jinja2 import Environment, FileSystemLoader, select_autoescape

# the variables staff can use, with what they stand for (listed on the email page)
VARIABLES = {
    'NAME': "The student's first name",
    'COURSE': 'The course',
    'EXAM': 'The exam',
    'ROOM': "The student's room",
    'SEAT': "The student's seat",
    'START_TIME': 'When the exam starts in that room',
    'DURATION': 'How long the exam is',
    'URL': "A link to the student's seat on the seating chart",
    'SEAT_DETAILS_LIST': 'The course, exam, room, seat, start time and duration, as a list',
}
SEAT_DETAILS = [('Course', 'COURSE'), ('Exam', 'EXAM'), ('Room', 'ROOM'), ('Seat', 'SEAT'),
                ('Start Time', 'START_TIME'), ('Duration', 'DURATION')]
# the list only makes sense in the body
SUBJECT_VARIABLES = [name for name in VARIABLES if name != 'SEAT_DETAILS_LIST']

PLACEHOLDER = re.compile(r'\{\{\s*(\w+)\s*\}\}')
LINK = re.compile(r'https?://[^\s<>"]+')

_jinja = Environment(loader=FileSystemLoader(os.path.dirname(__file__)), autoescape=select_autoescape(['html']))


class EmailContent:
    def __init__(self, subject: str, body: str):
        self.subject = subject
        self.body = body

    def __repr__(self) -> str:
        return f'EmailContent(subject={self.subject}, body={self.body})'


def get_email(template: EmailTemplate) -> EmailContent:
    """The subject and plain-text body an email starts from, with their placeholders."""
    # template.value is the file name for email metadata (json), in the same folder as this file
    with open(os.path.join(os.path.dirname(__file__), template.value + ".json")) as f:
        email_metadata = json.load(f)
    with open(os.path.join(os.path.dirname(__file__), email_metadata['body_path'])) as f:
        body = f.read()
    return EmailContent(email_metadata['subject'], body)


def unknown_variables(text: str, known=VARIABLES) -> list[str]:
    """The placeholders of `text` that are not variables (a typo like {{ROOOM}}), in order."""
    unknown = [name for name in PLACEHOLDER.findall(text or '') if name not in known]
    return list(dict.fromkeys(unknown))


def make_substitutions(text: str, substitutions: dict[str, str]) -> str:
    """
    Fill in the {{KEY}} placeholders of plain `text`; others are left as they are. The values are
    taken literally: a name like "Jo\\hn" is not read as an escape.
    """
    return PLACEHOLDER.sub(lambda match: str(substitutions.get(match.group(1), match.group(0))), text)


def render_text(body: str, values: dict[str, str]) -> str:
    """The plain-text part: the body filled in, with the seat details as lines."""
    seat_details = '\n'.join(f'- {label}: {values[key]}' for label, key in SEAT_DETAILS)
    return make_substitutions(body, {**values, 'SEAT_DETAILS_LIST': seat_details})


def render_html(subject: str, body: str, values: dict[str, str]) -> str:
    """The HTML part, from assignment_email.html: the template escapes every piece of `body`."""
    return _jinja.get_template('assignment_email.html').render(
        subject=subject, blocks=_blocks(body, values),
        seat_details=[(label, values[key]) for label, key in SEAT_DETAILS])


def _blocks(body, values):
    """
    `body` as the template's blocks: 'seat_details' for the list, or a paragraph as a list of
    (kind, value) pieces, kind being 'text', 'link' or 'break'. Blank lines separate paragraphs; the
    list stands on its own, since a list can't sit inside a paragraph.
    """
    blocks = []
    for chunk in re.split(r'\n\s*\n', body.replace('\r\n', '\n').strip()):
        for i, part in enumerate(re.split(r'\{\{\s*SEAT_DETAILS_LIST\s*\}\}', chunk)):
            if i:
                blocks.append('seat_details')
            paragraph = _pieces(part.strip(), values)
            if paragraph:
                blocks.append(paragraph)
    return blocks


def _pieces(text, values):
    pieces = []
    position = 0
    for match in PLACEHOLDER.finditer(text):
        pieces += _text_pieces(text[position:match.start()])
        name = match.group(1)
        if name not in values:
            pieces.append(('text', match.group(0)))
        else:
            pieces.append(('link' if name == 'URL' else 'text', str(values[name])))
        position = match.end()
    return pieces + _text_pieces(text[position:])


def _text_pieces(text):
    """Text typed by staff: its line breaks kept, and its http(s) links made clickable."""
    pieces = []
    for i, line in enumerate(text.split('\n')):
        if i:
            pieces.append(('break', None))
        position = 0
        for match in LINK.finditer(line):
            url = _without_trailing_punctuation(match.group(0))
            pieces.append(('text', line[position:match.start()]))
            pieces.append(('link', url))
            position = match.start() + len(url)
        pieces.append(('text', line[position:]))
    return [piece for piece in pieces if piece != ('text', '')]


def _without_trailing_punctuation(url):
    # "see https://x.edu/a." ends a sentence; keep a closing parenthesis that the link opened
    while url and (url[-1] in '.,;:!?\'"' or (url[-1] == ')' and url.count(')') > url.count('('))):
        url = url[:-1]
    return url
