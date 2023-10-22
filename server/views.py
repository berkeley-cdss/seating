from math import log
import re

from flask import abort, redirect, render_template, request, send_file, url_for, flash
from flask_login import current_user, login_required

from server import app
from server.models import db, Offering, Exam, Room, Seat, Student
from server.form import ExamForm, RoomForm, ChooseRoomForm, StudentForm, DeleteStudentForm, \
    AssignForm, EmailForm
from server.utils.auth import google_oauth
import server.utils.canvas as canvas_client
from server.utils.data import validate_room, validate_students
from server.utils.exception import DataValidationError
from server.utils.url import apply_converter, format_offering_url
from server.utils.assign import assign_students
from server.utils.email import email_students

apply_converter()

# region Offering CRUDI


@app.route('/')
@login_required
def index():
    """
    Path: /
    Home page, which needs to be logged in to access.
    After logging in, fetch and present a list of course offerings.
    """
    user = canvas_client.get_user(current_user.canvas_id)
    offerings = []
    for c in canvas_client.get_user_courses(user):
        offering = Offering(
            canvas_id=c['id'],
            name=c['name'],
            code=c['course_code'])
        offerings.append(offering)
    return render_template("select_offering.html.j2",
                           title="Select a Course Offering", offerings=offerings)


@app.route('/<offering:offering>/')
def offering(offering):
    """
    Path: /offerings/<canvas_id>
    Shows all exams created for a course offering.
    """
    exams = Exam.query.filter(Exam.offering_canvas_id == offering.canvas_id)
    return render_template("select_exam.html.j2",
                           exams=exams, offering=offering)

# endregion

# region Exam CRUDI


@app.route("/<offering:offering>/exams/new/", methods=["GET", "POST"])
def new_exam(offering):
    """
    Path: /offerings/<canvas_id>/exams/new
    Creates a new exam for a course offering.
    """
    form = ExamForm()
    if form.validate_on_submit():
        Exam.query.filter_by(offering_canvas_id=offering.canvas_id).update({"is_active": False})
        try:
            exam = Exam(offering_canvas_id=offering.canvas_id,
                        name=form.name.data,
                        display_name=form.display_name.data,
                        is_active=True)
            db.session.add(exam)
            db.session.commit()
            print("exam", exam.offering_canvas_id, exam.name)
            print("offering", offering)
            return redirect(url_for('offering', offering=offering))
        except:
            db.session.rollback()
            abort(400, "Exam name {} already exists for this offering.".format(
                form.name.data))
            return redirect(url_for('offering', offering=offering))
    return render_template("new_exam.html.j2",
                           title="Create an Exam for {}".format(offering.name),
                           form=form)


@app.route("/<exam:exam>/delete/", methods=["GET", "DELETE"])
def delete_exam(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/delete
    Deletes an exam for a course offering.
    """
    db.session.delete(exam)
    db.session.commit()
    return redirect(url_for('offering', offering=exam.offering))


@app.route("/<exam:exam>/toggle/", methods=["GET", "PATCH"])
def toggle_exam(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/toggle
    Toggles an exam for a course offering.
    """
    if exam.is_active:
        exam.is_active = False
    else:
        # only one exam can be active at a time, so deactivate all others first
        Exam.query.filter_by(offering_canvas_id=exam.offering_canvas_id).update(
            {"is_active": False})
        exam.is_active = True
    db.session.commit()
    return redirect(url_for('offering', offering=exam.offering))


@app.route('/<exam:exam>/')
def exam(exam):
    return render_template('exam.html.j2', exam=exam)
# endregion

# region Room CRUDI


@app.route('/<exam:exam>/rooms/import/')
@google_oauth.required(scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
def import_room(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/import
    """
    new_form = RoomForm()
    choose_form = ChooseRoomForm()
    return render_template('new_room.html.j2',
                           exam=exam, new_form=new_form, choose_form=choose_form)


@app.route('/<exam:exam>/rooms/import/new/', methods=['GET', 'POST'])
@google_oauth.required(scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
def new_room(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/import/new
    """
    new_form = RoomForm()
    choose_form = ChooseRoomForm()
    room = None
    if new_form.validate_on_submit():
        try:
            room = validate_room(exam, new_form)
        except Exception as e:
            new_form.sheet_url.errors.append(str(e))
        if new_form.create_room.data:
            try:
                db.session.add(room)
                db.session.commit()
                # TODO: proper error handling
            except:
                new_form.sheet_url.errors.append(
                    "Room name {} already exists for this exam.".format(room.name))
            return redirect(url_for('exam', exam=exam))
    return render_template('new_room.html.j2',
                           exam=exam, new_form=new_form, choose_form=choose_form, room=room)


MASTER_ROOM_SHEET = 'https://docs.google.com/spreadsheets/d/' + \
    '1cHKVheWv2JnHBorbtfZMW_3Sxj9VtGMmAUU2qGJ33-s/edit?usp=sharing'


@app.route('/<exam:exam>/rooms/import/choose/', methods=['GET', 'POST'])
@google_oauth.required(scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
def choose_room(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/import/choose
    """
    new_form = RoomForm()
    choose_form = ChooseRoomForm()
    if choose_form.validate_on_submit():
        for r in choose_form.rooms.data:
            f = RoomForm(
                display_name=r,
                sheet_url=MASTER_ROOM_SHEET, sheet_range=r)
            room = None
            try:
                room = validate_room(exam, f)
                # TODO: proper error handling
            except Exception as e:
                choose_form.rooms.errors.append(str(e))
            if room:
                db.session.add(room)
                db.session.commit()
            return redirect(url_for('exam', exam=exam))
    return render_template('new_room.html.j2',
                           exam=exam, new_form=new_form, choose_form=choose_form)


@app.route('/<exam:exam>/rooms/<string:name>/delete', methods=['DELETE'])
def delete_room(exam, name):
    room = Room.query.filter_by(exam_id=exam.id, name=name).first_or_404()
    if room:
        seats = Seat.query.filter_by(room_id=room.id).all()
        for seat in seats:
            if seat.assignment:
                db.session.delete(seat.assignment)
            db.session.delete(seat)
        db.session.delete(room)
        db.session.commit()
    return render_template('exam.html.j2', exam=exam)


@app.route('/<exam:exam>/rooms/<string:name>/')
def room(exam, name):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/<room_name>
    Displays the room diagram, with an optional seat highlighted.
    """
    room = Room.query.filter_by(exam_id=exam.id, name=name).first_or_404()
    seat = request.args.get('seat')
    return render_template('room.html.j2', exam=exam, room=room, seat=seat)
# endregion

# region Student CRUDI


@app.route('/<exam:exam>/students/import/', methods=['GET', 'POST'])
@google_oauth.required(scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
def new_students(exam):
    form = StudentForm()
    if form.validate_on_submit():
        try:
            students = validate_students(exam, form)
            db.session.add_all(students)
            db.session.commit()
            return redirect(url_for('exam', exam=exam))
        except DataValidationError as e:
            form.sheet_url.errors.append(str(e))
    return render_template('new_students.html.j2', exam=exam, form=form)


@app.route('/<exam:exam>/students/delete/', methods=['GET', 'POST'])
def delete_students(exam):
    form = DeleteStudentForm()
    deleted, did_not_exist = set(), set()
    if form.validate_on_submit():
        for email in re.split(r'\s|,', form.emails.data):
            if not email:
                continue
            student = Student.query.filter_by(
                exam_id=exam.id, email=email).first()
            if student:
                deleted.add(email)
                if student.assignment:
                    db.session.delete(student.assignment)
                # TODO: should probabaly use bulk deletion
                db.session.delete(student)
            else:
                did_not_exist.add(email)
        db.session.commit()
    return render_template('delete_students.html.j2',
                           exam=exam, form=form, deleted=deleted, did_not_exist=did_not_exist)


@app.route('/<exam:exam>/students/')
def students(exam):
    # TODO load assignment and seat at the same time?
    return render_template('students.html.j2', exam=exam, students=exam.students)


@app.route('/<exam:exam>/students/<string:canvas_id>/')
def student(exam, canvas_id):
    student = Student.query.filter_by(
        exam_id=exam.id, canvas_id=canvas_id).first_or_404()
    return render_template('student.html.j2', exam=exam, student=student)


@app.route('/<exam:exam>/students/<string:canvas_id>/delete', methods=['GET', 'DELETE'])
def delete_student(exam, canvas_id):
    student = Student.query.filter_by(
        exam_id=exam.id, canvas_id=canvas_id).first_or_404()
    if student:
        if student.assignment:
            db.session.delete(student.assignment)
        db.session.delete(student)
        db.session.commit()
    return render_template('students.html.j2',
                           exam=exam, students=exam.students)
# endregion


@app.route('/<exam:exam>/students/assign/', methods=['GET', 'POST'])
def assign(exam):
    form = AssignForm()
    if form.validate_on_submit():
        assignments = assign_students(exam)
        if isinstance(assignments, str):
            return assignments
        db.session.add_all(assignments)
        db.session.commit()
        return redirect(url_for('students', exam=exam))
    return render_template('assign.html.j2', exam=exam, form=form)


@app.route('/<exam:exam>/students/email/', methods=['GET', 'POST'])
def email(exam):
    form = EmailForm()
    if form.validate_on_submit():
        email_students(exam, form)
        return redirect(url_for('students', exam=exam))
    return render_template('email.html.j2', exam=exam, form=form)

# region Misc


@app.route('/help/')
@login_required
def help():
    return render_template('help.html.j2', title="Help")
# endregion


@app.route('/favicon.ico')
def favicon():
    return send_file('static/img/favicon.ico')


@app.route('/students-template.png')
def students_template():
    return send_file('static/img/students-template.png')


@app.route('/<exam:exam>/students/photos/', methods=['GET', 'POST'])
def new_photos(exam):
    return render_template('new_photos.html.j2', exam=exam)


@app.route('/<exam:exam>/students/<string:email>/photo')
def photo(exam, email):
    student = Student.query.filter_by(
        exam_id=exam.id, email=email).first_or_404()
    photo_path = '{}/{}/{}.jpeg'.format(app.config['PHOTO_DIRECTORY'],
                                        exam.offering_canvas_id, student.bcourses_id)
    return send_file(photo_path, mimetype='image/jpeg')


@app.route('/seat/<int:seat_id>/')
def single_seat(seat_id):
    seat = Seat.query.filter_by(id=seat_id).first_or_404()
    return render_template('seat.html.j2', room=seat.room, seat=seat)
