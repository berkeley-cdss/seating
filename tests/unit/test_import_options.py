"""
The options of the student import page, sent the way the page sends them (issue #58). They used to
arrive as strings that never matched the import's enums, so every choice was ignored: "remove students
not in the import" removed nobody, and so on. Each test posts the real form.
The seed exam has Jimmy Xu (234567, seated in seat 1), Sharon Lovera (345678) and Lavender Angela
(456789); the mock Canvas roster of the course has the same three students.
"""
import re

import pytest

import server.services.core.data as data
from server.models import db, Seat, SeatAssignment, Student
from server.services.core.student import StudentImportConfig
from server.typings.enum import MissingRowImportStrategy, UpdatedRowImportStrategy

EXAM_URL = '/offerings/1234567/exams/midterm1'
DEFAULTS = {
    'revalidate_existing_assignments': 'y',
    'assignment_import_strategy': 'revalidate',
    'updated_student_info_import_strategy': 'merge',
    'updated_preference_import_strategy': 'merge',
    'new_student_import_strategy': 'append',
    'missing_student_import_strategy': 'ignore',
}


def _student(canvas_id):
    db.session.expire_all()
    return Student.query.filter_by(exam_id=1, canvas_id=canvas_id).one_or_none()


@pytest.fixture
def staff(seeded_db, login_as):
    return login_as(1)


def _post(client, source, **options):
    page = client.get(f'{EXAM_URL}/students/import/').get_data(as_text=True)
    data = {'csrf_token': re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1),
            **DEFAULTS, **options}
    data = {key: value for key, value in data.items() if value is not None}
    # the Canvas roster button posts the same form elsewhere; files, pasted rows and sheet links to the page
    url = f'{EXAM_URL}/students/import/' + ('from_canvas_roster/' if source == 'canvas_roster' else '')
    response = client.post(url, data=data, follow_redirects=True)
    return [' '.join(message.split()) for message in
            re.findall(r'<span class="alert-message">(.*?)</span>', response.get_data(as_text=True), re.S)]


def _manual(client, text, **options):
    return _post(client, 'paste', text=text, **options)


@pytest.fixture
def jimmy_dropped(monkeypatch):
    """Jimmy Xu has left the course in bCourses: the Canvas roster no longer lists him."""
    roster = data.get_student_roster_for_offering

    def roster_without_jimmy(offering_canvas_id, key=None):
        headers, rows = roster(offering_canvas_id, key)
        return headers, [row for row in rows if str(row.get('canvas id')) != '234567']

    monkeypatch.setattr(data, 'get_student_roster_for_offering', roster_without_jimmy)


def test_roster_import_removes_students_who_dropped(staff, jimmy_dropped):
    assert _student('234567').assignment is not None
    messages = _post(staff, 'canvas_roster', missing_student_import_strategy='delete')
    assert 'Import done. 0 new students, 2 updated students 0 invalid students. 1 students removed.' in messages
    assert 'Removed students not in the import: Jimmy Xu' in messages
    assert _student('234567') is None
    # their seat is free again
    assert SeatAssignment.query.filter_by(seat_id=1).count() == 0
    assert _student('345678') is not None and _student('456789') is not None


def test_roster_import_keeps_students_who_dropped_by_default(staff, jimmy_dropped):
    messages = _post(staff, 'canvas_roster')
    assert any('0 students removed' in message for message in messages)
    assert _student('234567').assignment is not None


def test_seat_that_does_not_fit_kept_preferences_is_not_used(staff):
    # Sharon wants a lefty seat (seed); the import does not mention preferences, so she keeps hers and
    # seat 2, a righty seat, does not fit. (Replacing preferences used to wipe hers, and seat her.)
    _manual(staff, 'canvas id,email,name,seat id\n345678,sharon@berkeley.edu,Sharon Lovera,2\n')
    assert _student('345678').wants == {'Lefty'} and _student('345678').assignment is None


def test_roster_import_keeps_preferences(staff):
    # the roster has no preference columns: by default it must not clear the ones students have
    sharon = _student('345678')
    sharon.wants, sharon.avoids = {'lefty'}, {'broken'}
    db.session.commit()
    _post(staff, 'canvas_roster')
    assert (_student('345678').wants, _student('345678').avoids) == ({'lefty'}, {'broken'})


@pytest.mark.parametrize('strategy', ['merge', 'overwrite', 'ignore'])
def test_roster_import_ignores_the_preference_option(staff, strategy):
    # the roster has no preferences: replacing students' with its none used to clear them all
    _post(staff, 'canvas_roster', updated_preference_import_strategy=strategy)
    assert _student('345678').wants == {'Lefty'}


def test_roster_import_ignores_revalidating(staff, sharon_wants_the_impossible):
    # Sharon was given seat 2 on purpose though it doesn't fit; the roster changes no preferences,
    # so it has no reason to unseat her
    _student('345678').assignment = SeatAssignment(seat=db.session.get(Seat, 2))
    db.session.commit()
    _post(staff, 'canvas_roster', revalidate_existing_assignments='y')
    assert _student('345678').assignment.seat_id == 2


def test_basic_info_keep(staff):
    _manual(staff, 'canvas id,email,name\n345678,new@berkeley.edu,New Name\n', updated_student_info_import_strategy='ignore')
    assert (_student('345678').name, _student('345678').email) == ('Sharon Lovera', 'sharon@berkeley.edu')


def test_basic_info_update_and_replace(staff):
    _manual(staff, 'canvas id,email,name,student id\n345678,,New Name,\n')
    assert (_student('345678').name, _student('345678').email) == ('New Name', 'sharon@berkeley.edu')
    _manual(staff, 'canvas id,email,name,student id\n345678,x@berkeley.edu,Other Name,\n',
            updated_student_info_import_strategy='overwrite')
    assert (_student('345678').name, _student('345678').email, _student('345678').sid) == \
        ('Other Name', 'x@berkeley.edu', None)


@pytest.mark.parametrize('strategy, wants', [
    ('merge', {'lefty', 'aisle'}),
    ('overwrite', {'aisle'}),
    ('ignore', {'lefty'}),
])
def test_preferences(staff, strategy, wants):
    sharon = _student('345678')
    sharon.wants = {'lefty'}
    db.session.commit()
    _manual(staff, 'canvas id,email,name,aisle\n345678,sharon@berkeley.edu,Sharon Lovera,true\n',
            updated_preference_import_strategy=strategy)
    assert _student('345678').wants == wants


def test_new_students_skip(staff):
    _manual(staff, 'canvas id,email,name\n777777,new@berkeley.edu,New Student\n', new_student_import_strategy='ignore')
    assert _student('777777') is None
    _manual(staff, 'canvas id,email,name\n777777,new@berkeley.edu,New Student\n')
    assert _student('777777') is not None


@pytest.fixture
def sharon_wants_the_impossible(staff):
    # no seat fits Sharon, so only "always use it" can seat her
    sharon = _student('345678')
    sharon.wants = {'no such attribute'}
    db.session.commit()


@pytest.mark.parametrize('strategy, seated', [('revalidate', False), ('force', True), ('ignore', False)])
def test_seats_listed_in_the_import(staff, sharon_wants_the_impossible, strategy, seated):
    _manual(staff, 'canvas id,email,name,seat id\n345678,sharon@berkeley.edu,Sharon Lovera,2\n',
            assignment_import_strategy=strategy, updated_preference_import_strategy='ignore')
    assert (_student('345678').assignment is not None) == seated


@pytest.fixture
def sharon_has_no_preferences(staff):
    # in the seed Sharon wants a lefty seat, and seat 2 is not one
    sharon = _student('345678')
    sharon.wants = set()
    db.session.commit()


def test_seat_in_the_import_is_used_when_it_fits(staff, sharon_has_no_preferences):
    _manual(staff, 'canvas id,email,name,seat id\n345678,sharon@berkeley.edu,Sharon Lovera,2\n')
    assert _student('345678').assignment.seat_id == 2


@pytest.mark.parametrize('options', [
    {'updated_student_info_import_strategy': 'ignore'},  # used to leave `emailed` undefined
    {'revalidate_existing_assignments': None},  # unchecked; used to leave the preferences undefined
])
def test_seat_column_with_options_that_used_to_crash(staff, sharon_has_no_preferences, options):
    messages = _manual(staff, 'canvas id,email,name,seat id\n345678,sharon@berkeley.edu,Sharon Lovera,2\n', **options)
    assert not any('unexpected error' in message for message in messages), messages
    assert _student('345678').assignment.seat_id == 2


def test_skipped_row_leaves_the_student_as_it_was(staff):
    jimmy = _student('234567')
    jimmy.avoids = {'lefty'}
    db.session.commit()
    messages = _manual(staff, 'canvas id,email,name,lefty\n234567,renamed@berkeley.edu,Renamed,true\n')
    assert any('both wants and avoids lefty' in message for message in messages)
    jimmy = _student('234567')
    assert (jimmy.name, jimmy.email, jimmy.wants, jimmy.avoids) == ('Jimmy Xu', 'jx@berkeley.edu', set(), {'lefty'})


def test_new_student_gets_the_import_values_whatever_the_update_options(staff):
    _manual(staff, 'canvas id,email,name,lefty\n777777,new@berkeley.edu,New Student,true\n',
            updated_student_info_import_strategy='ignore', updated_preference_import_strategy='ignore')
    new = _student('777777')
    assert (new.name, new.email, new.wants, new.avoids) == ('New Student', 'new@berkeley.edu', {'lefty'}, set())


def test_page_explains_the_options_and_confirms_removing(staff):
    page = staff.get(f'{EXAM_URL}/students/import/').get_data(as_text=True)
    assert 'Students in this exam but not in the import:' in page
    assert 'Remove them, and their seat assignment' in page
    assert "select.value === 'delete' &amp;&amp; !confirm(" in page or "select.value === 'delete' && !confirm(" in page


def test_config_takes_values_or_enums():
    config = StudentImportConfig(missing_student_import_strategy='delete',
                                 updated_preference_import_strategy=UpdatedRowImportStrategy.OVERWRITE)
    assert config.missing_student_import_strategy is MissingRowImportStrategy.DELETE
    assert config.updated_preference_import_strategy is UpdatedRowImportStrategy.OVERWRITE
    assert StudentImportConfig().updated_preference_import_strategy is UpdatedRowImportStrategy.MERGE
    with pytest.raises(ValueError):
        StudentImportConfig(missing_student_import_strategy='remove')
