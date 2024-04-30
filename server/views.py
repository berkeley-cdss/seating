import re
from flask import abort, redirect, render_template, request, send_file, url_for, flash, Response
from flask.json import jsonify
from flask_login import current_user, login_required

from server import app
from server.models import SeatAssignment, db, Exam, Room, Seat, Student
from server.forms import AssignSingleForm, EditExamForm, EditRoomForm, ExamForm, ImportStudentFromCsvUploadForm, \
    RoomForm, ChooseRoomForm, ImportStudentFromSheetForm, ImportStudentFromCanvasRosterForm, DeleteStudentForm, \
    AssignForm, EmailForm, EditStudentForm, UploadRoomForm, ChooseCourseOfferingForm, EditStudentsForm, \
    ImportStudentFromManualInputForm
from server.services.core.export import export_exam_student_info
from server.services.email.templates import get_email
from server.services.google import get_spreadsheet_tabs
import server.services.canvas as canvas_client
from server.services.email import email_about_assignment, substitute_about_assignment
from server.services.core.data import get_room_from_csv, get_room_from_google_spreadsheet, get_room_from_manual_input, \
    get_students_from_canvas, get_students_from_csv, get_students_from_google_spreadsheet, update_room_from_manual_input, \
    get_students_from_manual_input
from server.services.core.assign import assign_single_student, assign_students
from server.typings.exception import NotEnoughSeatError, SeatAssignmentError
from server.typings.enum import EmailTemplate
from server.utils.date import to_ISO8601
from server.utils.misc import set_to_str, str_set_to_set


@app.route('/')
def index():
    """
    Path: /
    Home page, which is the login page.
    """
    # if already logged in, redirect to offerings page
    if current_user and current_user.is_authenticated:
        return redirect(url_for('offerings'))
    return render_template("index.html.j2")


# region Offering CRUDI


@app.route('/offerings')
@login_required
def offerings():
    from server.models import Offering
    """
    Path: /offerings
    Home page, which needs to be logged in to access.
    After logging in, fetch and present a list of course offerings.
    """
    # Fetch all user course offerings from canvas
    user = canvas_client.get_user(current_user.canvas_id)
    staff_course_dics, student_course_dics, others, skipped = canvas_client.get_user_courses_categorized(
        user)
    # All fetched courses are converted to models
    staff_offerings = [canvas_client.api_course_to_model(c) for c in staff_course_dics]
    student_offerings = [canvas_client.api_course_to_model(c) for c in student_course_dics]
    other_offerings = [canvas_client.api_course_to_model(c) for c in others]
    # Check which offerings are already in the database
    staff_offering_canvas_ids = set([o.canvas_id for o in staff_offerings])
    student_offering_canvas_ids = set([o.canvas_id for o in student_offerings])
    other_offering_canvas_ids = set([o.canvas_id for o in other_offerings])
    wanted_offering_canvas_ids = staff_offering_canvas_ids | student_offering_canvas_ids | other_offering_canvas_ids
    existing_offerings = Offering.query.filter(
        Offering.canvas_id.in_(wanted_offering_canvas_ids)).all()
    # Now split existing_offerings back to 3 lists
    staff_offerings_existing = []
    student_offerings_existing = []
    other_offerings_existing = []
    for o in existing_offerings:
        if o.canvas_id in staff_offering_canvas_ids:
            staff_offerings_existing.append(o)
        elif o.canvas_id in student_offering_canvas_ids:
            student_offerings_existing.append(o)
        elif o.canvas_id in other_offering_canvas_ids:
            other_offerings_existing.append(o)

    if skipped:
        flash("Skipped invalid courses from Canvas: " + str([s.__dict__ for s in skipped]), 'warning')

    return render_template("select_offering.html.j2",
                           title="Select a Course Offering",
                           staff_offerings_existing=staff_offerings_existing,
                           student_offerings_existing=student_offerings_existing,
                           other_offerings_existing=other_offerings_existing)


@app.route('/offerings/new', methods=['GET', 'POST'])
@login_required
def add_offerings():
    from server.models import Offering
    """
    Path: /offerings/new
    Add new course offerings to the database.
    """
    user = canvas_client.get_user(current_user.canvas_id)
    staff_course_dics, _, _, skipped = canvas_client.get_user_courses_categorized(user)
    staff_offerings = [canvas_client.api_course_to_model(o) for o in staff_course_dics]
    staff_offerings_id_to_model = {o.canvas_id: o for o in staff_offerings}
    staff_offering_ids_wanted = list(staff_offerings_id_to_model.keys())
    staff_offering_ids_existing = set([x[0] for x in Offering.query.filter(
        Offering.canvas_id.in_(staff_offering_ids_wanted)).with_entities(Offering.canvas_id)])
    staff_offering_ids_not_existing = set(staff_offering_ids_wanted) - staff_offering_ids_existing
    if skipped:
        flash("Skipped invalid courses from Canvas: " + str([s.__dict__ for s in skipped]), 'warning')
    if not staff_offering_ids_not_existing:
        flash("No more new courses to import.", 'info')
        return redirect(url_for('offerings'))
    staff_offerings_not_existing = [staff_offerings_id_to_model[canvas_id] for canvas_id in staff_offering_ids_not_existing]
    form = ChooseCourseOfferingForm(offering_list=staff_offerings_not_existing)
    if form.validate_on_submit():
        to_be_saved = [staff_offerings_id_to_model[canvas_id] for canvas_id in form.offerings.data]
        if not to_be_saved:
            flash("No course offering imported.", 'info')
            return redirect(url_for('offerings'))
        try:
            db.session.bulk_save_objects(to_be_saved)
            db.session.commit()
            flash(f"Imported {len(to_be_saved)} course offerings.", 'success')
            return redirect(url_for('offerings'))
        except Exception as e:
            db.session.rollback()
            print("error", str(e))
            flash("An error occurred when inserting offering: " + str(e), 'error')
    return render_template("new_offerings.html.j2",
                           title="Add New Course Offerings",
                           form=form)


@app.route('/<offering:offering>/')
def offering(offering):
    """
    Path: /offerings/<canvas_id>
    Shows all exams created for a course offering.
    """
    is_staff = str(offering.canvas_id) in current_user.staff_offerings
    all_exams = offering.exams
    active_exams = [e for e in all_exams if e.is_active]
    inactive_exams = [e for e in all_exams if not e.is_active]
    return render_template("select_exam.html.j2",
                           title="Select an Exam for {}".format(offering.name),
                           active_exams=active_exams,
                           inactive_exams=inactive_exams,
                           all_exams=all_exams,
                           offering=offering,
                           is_staff=is_staff)


@app.route('/<offering:offering>/delete/', methods=['GET', 'DELETE'])
def delete_offering(offering):
    """
    Path: /offerings/<canvas_id>/delete
    Deletes a course offering.
    """
    # offering urls convertor only checks login but does not check staff status
    # we need to do it here
    if str(offering.canvas_id) not in current_user.staff_offerings:
        abort(403, "You are not a staff member in this offering.")
    try:
        db.session.delete(offering)
        db.session.commit()
        flash("Deleted offering.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to delete offering {offering.name} (Canvas ID: {offering.canvas_id}) due to an error:\n{e}", 'error')
    return redirect(url_for('offerings'))


# endregion

# region Exam CRUDI


@app.route("/<offering:offering>/exams/new/", methods=["GET", "POST"])
def new_exam(offering):
    """
    Path: /offerings/<canvas_id>/exams/new
    Creates a new exam for a course offering.
    """
    # offering urls convertor only checks login but does not check staff status
    # we need to do it here
    if str(offering.canvas_id) not in current_user.staff_offerings:
        abort(403, "You are not a staff member in this offering.")
    form = ExamForm()
    if form.validate_on_submit():
        offering.mark_all_exams_as_inactive()
        try:
            exam = Exam(offering_canvas_id=offering.canvas_id,
                        name=form.name.data,
                        display_name=form.display_name.data,
                        is_active=True)
            db.session.add(exam)
            db.session.commit()
            return redirect(url_for('offering', offering=offering))
        except Exception as e:
            db.session.rollback()
            flash(f"An error occurred when inserting exam of name={form.name.data}\n{str(e)}", 'error')
            return redirect(url_for('offering', offering=offering))
    return render_template("upsert_exam.html.j2",
                           title="Create an Exam for {}".format(offering.name),
                           form=form, exam=None)


@app.route("/<exam:exam>/delete/", methods=["GET", "DELETE"])
def delete_exam(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/delete
    Deletes an exam for a course offering.
    """
    try:
        db.session.delete(exam)
        db.session.commit()
        flash("Deleted exam.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to delete exam {exam.display_name} (ID: {exam.id}) due to an error:\n{e}", 'error')
    return redirect(url_for('offering', offering=exam.offering))


@app.route("/<exam:exam>/edit/", methods=["GET", "POST"])
def edit_exam(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/edit
    Edits an exam for a course offering.
    """
    form = EditExamForm()
    if request.method == 'GET':
        form.display_name.data = exam.display_name
        form.active.data = exam.is_active
    if form.validate_on_submit():
        if 'cancel' in request.form:
            return redirect(url_for('offering', offering=exam.offering))
        exam.display_name = form.display_name.data
        if form.active.data:
            exam.offering.mark_all_exams_as_inactive()
            exam.is_active = True
        else:
            exam.is_active = False
            if exam.offering.ensure_one_exam_is_active():
                flash("No active exam left. The first exam is activated by default.", 'info')
        try:
            db.session.commit()
            return redirect(url_for('offering', offering=exam.offering))
        except Exception as e:
            db.session.rollback()
            flash(f"Failed to edit exam name={exam.display_name} due to a db error: \n{e}", 'error')
            return redirect(url_for('offering', offering=exam.offering))
    return render_template("upsert_exam.html.j2",
                           title="Edit Exam: {}".format(exam.display_name),
                           form=form, exam=exam)


@app.route("/<exam:exam>/toggle/", methods=["GET", "PATCH"])
def toggle_exam(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/toggle
    Toggles an exam for a course offering.
    """
    if exam.is_active:
        exam.is_active = False
        if exam.offering.ensure_one_exam_is_active():
            flash("No active exam left. The first exam is activated by default.", 'info')
    else:
        # only one exam can be active at a time, so deactivate all others first
        exam.offering.mark_all_exams_as_inactive()
        exam.is_active = True
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to toggle exam name={exam.display_name} due to a db error: \n{e}", 'error')
    return redirect(url_for('offering', offering=exam.offering))


@app.route('/<exam:exam>/')
def exam(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>
    Front page for an exam, which essentially shows all rooms created for an exam.
    """
    return render_template('exam.html.j2', exam=exam)
# endregion

# region Room CRUDI


@app.route('/<exam:exam>/rooms/import/')
def import_room(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/import
    """
    new_form = RoomForm()
    choose_form = ChooseRoomForm(room_list=get_spreadsheet_tabs(app.config.get('MASTER_ROOM_SHEET_URL')))
    upload_form = UploadRoomForm()
    return render_template('new_room.html.j2',
                           exam=exam, new_form=new_form, choose_form=choose_form,
                           upload_form=upload_form,
                           master_sheet_url=app.config.get('MASTER_ROOM_SHEET_URL'))


@app.route('/<exam:exam>/rooms/import/from_custom_sheet/', methods=['GET', 'POST'])
def import_room_from_custom_sheet(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/import/new
    """
    new_form = RoomForm()
    choose_form = ChooseRoomForm()
    upload_form = UploadRoomForm()
    room = None
    if new_form.validate_on_submit():
        try:
            room = get_room_from_google_spreadsheet(exam, new_form)
        except Exception as e:
            flash(f"Failed to import room due to an unexpected error: {e}", 'error')
        if new_form.create_room.data:
            try:
                db.session.add(room)
                db.session.commit()
            except Exception as e:
                flash(f"Failed to import room due to an db error: {e}", 'error')
            return redirect(url_for('exam', exam=exam))
    for field, errors in new_form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('new_room.html.j2',
                           exam=exam,
                           new_form=new_form, choose_form=choose_form,
                           upload_form=upload_form,
                           room=room,
                           master_sheet_url=app.config.get('MASTER_ROOM_SHEET_URL'))


@app.route('/<exam:exam>/rooms/import/from_master_sheet/', methods=['GET', 'POST'])
def import_room_from_master_sheet(exam):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/import/choose
    """
    new_form = RoomForm()
    choose_form = ChooseRoomForm(room_list=get_spreadsheet_tabs(app.config.get('MASTER_ROOM_SHEET_URL')))
    upload_form = UploadRoomForm()
    if choose_form.validate_on_submit():
        for r in choose_form.rooms.data:
            f = RoomForm(
                display_name=r,
                sheet_url=app.config.get("MASTER_ROOM_SHEET_URL"),
                sheet_range=r)
            room = None
            try:
                room = get_room_from_google_spreadsheet(exam, f)
            except Exception as e:
                flash(f"Failed to import room due to an unexpected error: {e}", 'error')
            if room:
                try:
                    db.session.add(room)
                    db.session.commit()
                except Exception as e:
                    flash(f"Failed to import room due to an db error: {e}", 'error')
        return redirect(url_for('exam', exam=exam))
    for field, errors in choose_form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('new_room.html.j2',
                           exam=exam,
                           new_form=new_form, choose_form=choose_form,
                           upload_form=upload_form,
                           master_sheet_url=app.config.get('MASTER_ROOM_SHEET_URL'))


@app.route('/<exam:exam>/rooms/import/from_csv_upload/', methods=['GET', 'POST'])
def import_room_from_csv_upload(exam):
    new_form = RoomForm()
    choose_form = ChooseRoomForm()
    upload_form = UploadRoomForm()
    if upload_form.validate_on_submit():
        room = None
        if upload_form.file.data:
            try:
                room = get_room_from_csv(exam, upload_form)
            except Exception as e:
                flash(f"Failed to import room due to an unexpected error: {e}", 'error')
        else:
            flash("No file uploaded!", 'error')
        if room:
            try:
                db.session.add(room)
                db.session.commit()
            except Exception as e:
                flash(f"Failed to import room due to a db error: {e}", 'error')
        return redirect(url_for('exam', exam=exam))
    for field, errors in upload_form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('new_room.html.j2',
                           exam=exam,
                           new_form=new_form, choose_form=choose_form,
                           upload_form=upload_form,
                           master_sheet_url=app.config.get('MASTER_ROOM_SHEET_URL'))


@app.route('/<exam:exam>/rooms/import/from_manual/', methods=['GET', 'POST'])
def import_room_manually(exam):
    form = EditRoomForm()
    if request.method == 'GET':
        if not form.movable_seats.entries:
            form.movable_seats.append_entry({
                'attributes': '',
                'count': 1
            })
    if form.validate_on_submit():
        from collections import defaultdict
        seats_to_add = defaultdict(int)
        for seat_form in form.movable_seats.data:
            seats_to_add[frozenset(str_set_to_set(seat_form['attributes']))] += max(0, seat_form['count'])
        room = None
        try:
            room = get_room_from_manual_input(exam, form, seats_to_add)
        except Exception as e:
            flash(f"Failed to import room due to an unexpected error: {e}", 'error')
        if room:
            try:
                db.session.add(room)
                db.session.commit()
            except Exception as e:
                flash(f"Failed to import room due to a db error: {e}", 'error')
        return redirect(url_for('exam', exam=exam))
    for field, errors in form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('upsert_room.html.j2', exam=exam, form=form, room=None)


@app.route('/<exam:exam>/rooms/<int:id>/delete', methods=['GET', 'DELETE'])
def delete_room(exam, id):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/<room_name>/delete
    Deletes a room for an exam.
    """
    room = Room.query.filter_by(exam_id=exam.id, id=id).first_or_404()
    if room:
        try:
            db.session.delete(room)
            db.session.commit()
            flash("Deleted room.", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Failed to delete room {room.display_name} (ID: {room.id}) due to an error:\n{e}", 'error')
    return render_template('exam.html.j2', exam=exam)


@app.route('/<exam:exam>/rooms/<int:id>/edit', methods=['GET', 'POST'])
def edit_room(exam, id):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/<room_name>/edit
    Edits a room for an exam.
    """
    room = Room.query.filter_by(exam_id=exam.id, id=id).first_or_404()
    form = EditRoomForm()
    if request.method == 'GET':
        form.display_name.data = room.display_name
        if room.start_at:
            form.start_at.data = room.start_at_time
        if room.duration_minutes:
            form.duration_minutes.data = room.duration_minutes
        for attr in room.movable_seats_by_attribute:
            form.movable_seats.append_entry({
                'attributes': set_to_str(attr),
                'count': len(room.movable_seats_by_attribute[attr])
            })
        if not form.movable_seats.entries:
            form.movable_seats.append_entry({
                'attributes': '',
                'count': 0
            })
    if form.validate_on_submit():
        if 'cancel' in request.form:
            return redirect(url_for('exam', exam=exam))
        # update other stuff
        room.display_name = form.display_name.data
        start_at_iso = None
        if form.start_at.data:
            start_at_iso = to_ISO8601(form.start_at.data)
        room.start_at = start_at_iso
        room.duration_minutes = form.duration_minutes.data
        # update movable seats
        from collections import defaultdict
        seats_to_add = defaultdict(int)
        for seat_form in form.movable_seats.data:
            seats_to_add[frozenset(str_set_to_set(seat_form['attributes']))] += max(0, seat_form['count'])
        try:
            update_room_from_manual_input(room, seats_to_add)
        except Exception as e:
            flash(f"Failed to edit room seats due to an unexpected error: {e}", 'error')
        try:
            db.session.commit()
        except Exception as e:
            flash(f"Failed to edit room due to a db error: {e}", 'error')
        return redirect(url_for('exam', exam=exam))
    return render_template('upsert_room.html.j2', exam=exam, form=form, room=room)


@app.route('/<exam:exam>/rooms/<int:id>/')
def room(exam, id):
    """
    Path: /offerings/<canvas_id>/exams/<exam_name>/rooms/<room_name>
    Displays the room diagram, with an optional seat highlighted.
    """
    # fetch all seat assignment at this point too to avoid N+1 problem
    # we will need to display the seat assignment in the room diagram
    from sqlalchemy.orm import joinedload
    room = Room.query.options(
        joinedload(Room.seats).joinedload(Seat.assignment)
    ).filter_by(exam_id=exam.id, id=id).first_or_404()
    seat_id = request.args.get('seat')
    return render_template('room.html.j2', exam=exam, room=room, seat_id=seat_id)
# endregion

# region Student CRUDI


@app.route('/<exam:exam>/students/import/')
def import_students(exam):
    from_sheet_form = ImportStudentFromSheetForm()
    from_canvas_form = ImportStudentFromCanvasRosterForm()
    from_csv_form = ImportStudentFromCsvUploadForm()
    from_manual_input_form = ImportStudentFromManualInputForm()
    return render_template('new_students.html.j2', exam=exam,
                           from_sheet_form=from_sheet_form,
                           from_canvas_form=from_canvas_form,
                           from_csv_form=from_csv_form,
                           from_manual_input_form=from_manual_input_form)


@app.route('/<exam:exam>/students/import/from_custom_sheet/', methods=['GET', 'POST'])
def import_students_from_custom_sheet(exam):
    from_sheet_form = ImportStudentFromSheetForm()
    from_canvas_form = ImportStudentFromCanvasRosterForm()
    from_csv_form = ImportStudentFromCsvUploadForm()
    from_manual_input_form = ImportStudentFromManualInputForm()
    if from_sheet_form.validate_on_submit():
        try:
            new_students, updated_students, invalid_students, students_ids_to_remove = get_students_from_google_spreadsheet(
                exam, from_sheet_form)
            to_commit = new_students + updated_students
            if students_ids_to_remove:
                Student.query.filter(Student.id.in_(students_ids_to_remove)).delete(synchronize_session=False)
            if to_commit:
                db.session.add_all(to_commit)
            if students_ids_to_remove or to_commit:
                db.session.commit()
            flash(
                f"Import done. {len(new_students)} new students, {len(updated_students)} updated students"
                f" {len(invalid_students)} invalid students. {len(students_ids_to_remove)} students removed.", 'success')
            if updated_students:
                flash(
                    f"Updated students: {set_to_str([s.name for s in updated_students])}", 'warning')
            if invalid_students:
                flash(
                    f"Invalid students: {invalid_students}", 'error')
        except Exception as e:
            flash(f"Failed to import students due to an unexpected error: {str(e)}", 'error')
        return redirect(url_for('students', exam=exam))
    for field, errors in from_sheet_form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('new_students.html.j2', exam=exam,
                           from_sheet_form=from_sheet_form,
                           from_canvas_form=from_canvas_form,
                           from_csv_form=from_csv_form,
                           from_manual_input_form=from_manual_input_form)


@app.route('/<exam:exam>/students/import/from_canvas_roster/', methods=['GET', 'POST'])
def import_students_from_canvas_roster(exam):
    from_sheet_form = ImportStudentFromSheetForm()
    from_canvas_form = ImportStudentFromCanvasRosterForm()
    from_csv_form = ImportStudentFromCsvUploadForm()
    from_manual_input_form = ImportStudentFromManualInputForm()
    if from_canvas_form.validate_on_submit():
        try:
            new_students, updated_students, invalid_students, students_ids_to_remove = get_students_from_canvas(
                exam, from_canvas_form)
            to_commit = new_students + updated_students
            if students_ids_to_remove:
                Student.query.filter(Student.id.in_(students_ids_to_remove)).delete(synchronize_session=False)
            if to_commit:
                db.session.add_all(to_commit)
            if students_ids_to_remove or to_commit:
                db.session.commit()
            flash(
                f"Import done. {len(new_students)} new students, {len(updated_students)} updated students"
                f" {len(invalid_students)} invalid students. {len(students_ids_to_remove)} students removed.", 'success')
            if updated_students:
                flash(
                    f"Updated students: {set_to_str([s.name for s in updated_students])}", 'warning')
            if invalid_students:
                flash(
                    f"Invalid students: {invalid_students}", 'error')
        except Exception as e:
            flash(f"Failed to import students due to an unexpected error: {str(e)}", 'error')
        return redirect(url_for('students', exam=exam))
    for field, errors in from_canvas_form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('new_students.html.j2', exam=exam,
                           from_sheet_form=from_sheet_form,
                           from_canvas_form=from_canvas_form,
                           from_csv_form=from_csv_form,
                           from_manual_input_form=from_manual_input_form)


@app.route('/<exam:exam>/students/import/from_csv_upload/', methods=['GET', 'POST'])
def import_students_from_csv_upload(exam):
    from_sheet_form = ImportStudentFromSheetForm()
    from_canvas_form = ImportStudentFromCanvasRosterForm()
    from_csv_form = ImportStudentFromCsvUploadForm()
    from_manual_input_form = ImportStudentFromManualInputForm()
    if from_csv_form.validate_on_submit():
        if from_csv_form.file.data:
            try:
                new_students, updated_students, invalid_students, students_ids_to_remove = get_students_from_csv(
                    exam, from_csv_form)
                to_commit = new_students + updated_students
                if students_ids_to_remove:
                    Student.query.filter(Student.id.in_(students_ids_to_remove)).delete(synchronize_session=False)
                if to_commit:
                    db.session.add_all(to_commit)
                if students_ids_to_remove or to_commit:
                    db.session.commit()
                flash(
                    f"Import done. {len(new_students)} new students, {len(updated_students)} updated students"
                    f" {len(invalid_students)} invalid students. {len(students_ids_to_remove)} students removed.", 'success')
                if updated_students:
                    flash(
                        f"Updated students: {set_to_str([s.name for s in updated_students])}", 'warning')
                if invalid_students:
                    flash(
                        f"Invalid students: {invalid_students}", 'error')
            except Exception as e:
                flash(f"Failed to import students due to an unexpected error: {str(e)}", 'error')
        else:
            flash("No file uploaded!", 'error')
        return redirect(url_for('students', exam=exam))
    for field, errors in from_csv_form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('new_students.html.j2', exam=exam,
                           from_sheet_form=from_sheet_form,
                           from_canvas_form=from_canvas_form,
                           from_csv_form=from_csv_form,
                           from_manual_input_form=from_manual_input_form)


@app.route('/<exam:exam>/students/import/from_manual_input/', methods=['GET', 'POST'])
def import_students_from_manual_input(exam):
    from_sheet_form = ImportStudentFromSheetForm()
    from_canvas_form = ImportStudentFromCanvasRosterForm()
    from_csv_form = ImportStudentFromCsvUploadForm()
    from_manual_input_form = ImportStudentFromManualInputForm()
    if from_manual_input_form.validate_on_submit():
        try:
            new_students, updated_students, invalid_students, students_ids_to_remove = get_students_from_manual_input(
                exam, from_manual_input_form)
            to_commit = new_students + updated_students
            if students_ids_to_remove:
                Student.query.filter(Student.id.in_(students_ids_to_remove)).delete(synchronize_session=False)
            if to_commit:
                db.session.add_all(to_commit)
            if students_ids_to_remove or to_commit:
                db.session.commit()
            flash(
                f"Import done. {len(new_students)} new students, {len(updated_students)} updated students"
                f" {len(invalid_students)} invalid students. {len(students_ids_to_remove)} students removed.", 'success')
            if updated_students:
                flash(
                    f"Updated students: {set_to_str([s.name for s in updated_students])}", 'warning')
            if invalid_students:
                flash(
                    f"Invalid students: {invalid_students}", 'error')
        except Exception as e:
            flash(f"Failed to import students due to an unexpected error: {str(e)}", 'error')
        return redirect(url_for('students', exam=exam))
    for field, errors in from_manual_input_form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('new_students.html.j2', exam=exam,
                           from_sheet_form=from_sheet_form,
                           from_canvas_form=from_canvas_form,
                           from_csv_form=from_csv_form,
                           from_manual_input_form=from_manual_input_form)


@app.route('/<exam:exam>/students/delete/', methods=['GET', 'POST'])
def delete_students(exam):
    form = DeleteStudentForm()
    deleted, did_not_exist = set(), set()
    if form.validate_on_submit():
        if not form.use_all_emails.data:
            emails = [x for x in str_set_to_set(form.emails.data) if x]
            students = Student.query.filter(
                Student.email.in_(emails) & (Student.exam_id == exam.id))
        else:
            students = Student.query.filter_by(exam_id=exam.id)
        deleted = {student.email for student in students}
        did_not_exist = set()
        if not form.use_all_emails.data:
            did_not_exist = set(emails) - deleted
        students.delete(synchronize_session=False)
        db.session.commit()
        if not deleted and not did_not_exist:
            abort(404, "No change has been made.")
    return render_template('delete_students.html.j2',
                           exam=exam, form=form, deleted=deleted, did_not_exist=did_not_exist)


@app.route('/<exam:exam>/students/')
def students(exam):
    # TODO load assignment and seat at the same time?
    return render_template('students.html.j2', exam=exam, students=exam.students)


@app.route('/<exam:exam>/students/export/csv')
def export_students_as_csv(exam):
    from datetime import datetime
    file_content = export_exam_student_info(exam)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    file_name = f"{exam.name}_students_{timestamp}.csv"
    return Response(
        file_content,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={file_name}"}
    )


@app.route('/<exam_student:exam_student>/edit', methods=['GET', 'POST'])
def edit_student(exam_student):
    exam, student = exam_student
    form = EditStudentForm(room_list=exam.rooms)
    edited, did_not_exist = set(), set()
    orig_wants_set = set(student.wants)
    orig_avoids_set = set(student.avoids)
    orig_room_wants_set = set(student.room_wants)
    orig_room_avoids_set = set(student.room_avoids)
    if request.method == 'GET':
        form.wants.data = set_to_str(orig_wants_set)
        form.avoids.data = set_to_str(orig_avoids_set)
        form.room_wants.data = set_to_str(orig_room_wants_set)
        form.room_avoids.data = set_to_str(orig_room_avoids_set)
        form.new_email.data = student.email
    if form.validate_on_submit():
        if 'cancel' in request.form:
            return redirect(url_for('students', exam=exam))
        new_wants_set = str_set_to_set(form.wants.data)
        new_avoids_set = str_set_to_set(form.avoids.data)
        new_room_wants_set = set(form.room_wants.data)
        new_room_avoids_set = set(form.room_avoids.data)
        # wants and avoids should not overlap
        if not new_wants_set.isdisjoint(new_avoids_set) \
                or not new_room_wants_set.isdisjoint(new_room_avoids_set):
            flash(
                "Wants and avoids should not overlap.\n"
                f"Want: {new_wants_set}\nAvoid: {new_avoids_set}\n"
                f"Room Want: {new_room_wants_set}\nRoom Avoid: {new_room_avoids_set}", 'error')
            return render_template('edit_student.html.j2', exam=exam, form=form, student=student)
        student.wants = new_wants_set
        student.avoids = new_avoids_set
        student.room_wants = new_room_wants_set
        student.room_avoids = new_room_avoids_set
        # if wants or avoids changed, delete original assignment
        # we need to compare sets because order does not matter
        if orig_wants_set != new_wants_set \
                or orig_avoids_set != new_avoids_set \
                or orig_room_wants_set != new_room_wants_set \
                or orig_room_avoids_set != new_room_avoids_set:
            if student.assignment:
                db.session.delete(student.assignment)
        student.email = form.new_email.data
        db.session.commit()
        return redirect(url_for('students', exam=exam))
    for field, errors in form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('edit_students.html.j2', exam=exam, form=form, edited=edited,
                           did_not_exist=did_not_exist, student=student)


@app.route('/<exam:exam>/students/edit', methods=['GET', 'POST'])
def edit_students(exam):
    form = EditStudentsForm(room_list=exam.rooms)
    edited, did_not_exist = set(), set()
    if form.validate_on_submit():
        if 'cancel' in request.form:
            return redirect(url_for('students', exam=exam))
        if not form.use_all_emails.data:
            emails = [x for x in re.split(r'\s|,', form.emails.data) if x]
            students = Student.query.filter(
                Student.email.in_(emails) & Student.exam_id == exam.id)
        else:
            students = Student.query.filter_by(exam_id=exam.id)
        edited = {student.email for student in students}
        did_not_exist = set()
        if not form.use_all_emails.data:
            did_not_exist = set(emails) - edited
        if not edited and not did_not_exist:
            abort(404, "No change has been made.")
        for student in students:
            new_wants_set = set(re.split(r'\s|,', form.wants.data)) if form.wants.data else set()
            new_avoids_set = set(re.split(r'\s|,', form.avoids.data)) if form.avoids.data else set()
            new_room_wants_set = set(form.room_wants.data)
            new_room_avoids_set = set(form.room_avoids.data)
            # wants and avoids should not overlap
            if not new_wants_set.isdisjoint(new_avoids_set) \
                    or not new_room_wants_set.isdisjoint(new_room_avoids_set):
                flash(
                    "Wants and avoids should not overlap.\n"
                    f"Want: {new_wants_set}\nAvoid: {new_avoids_set}\n"
                    f"Room Want: {new_room_wants_set}\nRoom Avoid: {new_room_avoids_set}", 'error')
                return render_template('edit_students.html.j2', exam=exam, form=form)
            orig_wants_set = set(student.wants)
            orig_avoids_set = set(student.avoids)
            orig_room_wants_set = set(student.room_wants)
            orig_room_avoids_set = set(student.room_avoids)
            student.wants = new_wants_set
            student.avoids = new_avoids_set
            student.room_wants = new_room_wants_set
            student.room_avoids = new_room_avoids_set
            # if wants or avoids changed, delete original assignment
            # we need to compare sets because order does not matter
            if orig_wants_set != new_wants_set \
                    or orig_avoids_set != new_avoids_set \
                    or orig_room_wants_set != new_room_wants_set \
                    or orig_room_avoids_set != new_room_avoids_set:
                if student.assignment:
                    db.session.delete(student.assignment)
        db.session.commit()
        # return redirect(url_for('students', exam=exam))
    for field, errors in form.errors.items():
        for error in errors:
            flash("{}: {}".format(field, error), 'error')
    return render_template('edit_students.html.j2', exam=exam, form=form, edited=edited,
                           did_not_exist=did_not_exist, student=None)


@app.route('/<exam_student:exam_student>/delete', methods=['GET', 'DELETE'])
def delete_student(exam_student):
    exam, student = exam_student
    if student:
        try:
            db.session.delete(student)
            db.session.commit()
            flash("Deleted student.", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Failed to delete student {student.name}"
                  f"(Canvas id: {student.canvas_id}) due to an error:\n{str(e)}", 'error')
    return redirect(url_for('students', exam=exam))


@app.route('/<exam:exam>/students/assign/', methods=['GET', 'POST'])
def assign(exam):
    form = AssignForm()
    if form.validate_on_submit():
        def delete_all_assignments_no_sync(e):
            seat_ids = {seat.id for room in e.rooms for seat in room.seats}
            SeatAssignment.query.filter(SeatAssignment.seat_id.in_(seat_ids)).delete(synchronize_session=False)
            db.session.commit()
        if 'delete_all' in request.form:
            delete_all_assignments_no_sync(exam)
            flash("Successfully deleted all assignments.", 'success')
            return redirect(url_for('students', exam=exam))
        elif 'reassign_all' in request.form:
            delete_all_assignments_no_sync(exam)
        try:
            assignments = assign_students(exam)
            db.session.add_all(assignments)
            db.session.commit()
            flash(f"Successfully assigned {len(assignments)} students.", 'success')
        except SeatAssignmentError as e:
            flash(str(e), 'error')
        return redirect(url_for('students', exam=exam))
    return render_template('assign.html.j2', exam=exam, form=form)


@app.route('/<exam_student:exam_student>/assign/', methods=['GET', 'POST'])
def assign_student(exam_student):
    form = AssignSingleForm()
    exam, student = exam_student
    if form.validate_on_submit():
        try:
            if 'just_delete' in request.form:
                if student.assignment:
                    db.session.delete(student.assignment)
                    db.session.commit()
                    flash(f"Successfully deleted assignment for {student.name}.", 'success')
                else:
                    flash(f"No assignment to delete for {student.name}.", 'warning')
                return redirect(url_for('students', exam=exam))
            chosen_seat = Seat.query.filter_by(id=form.seat_id.data).first_or_404() if form.seat_id.data != "" else None
            old_assignment = None
            if student.assignment:
                old_assignment = student.assignment
            assignment = assign_single_student(exam, student, chosen_seat, ignore_restrictions=form.ignore_restrictions.data)
            if old_assignment:
                db.session.delete(old_assignment)
            db.session.add(assignment)
            db.session.commit()
            flash(f"Successfully assigned {student.name}.", 'success')
        except SeatAssignmentError as e:
            flash(str(e), 'error')
        return redirect(url_for('students', exam=exam))
    return render_template('assign_single.html.j2', exam=exam, form=form)


@app.route('/<exam:exam>/students/email/', methods=['GET', 'POST'])
def email_all_students(exam):
    form = EmailForm()
    if form.validate_on_submit():
        successful_emails, failed_emails = email_about_assignment(exam, form, form.to_addr.data)
        if successful_emails:
            flash(f"Successfully emailed {len(successful_emails)} students.", 'success')
        if failed_emails:
            flash(f"Failed to email students: {set_to_str(failed_emails)}", 'error')
        if not successful_emails and not failed_emails:
            flash("No email sent.", 'warning')
        return redirect(url_for('students', exam=exam))
    else:
        email_prefill = get_email(EmailTemplate.ASSIGNMENT_INFORM_EMAIL)
        form.subject.data = email_prefill.subject
        form.body.data = email_prefill.body
        form.to_addr.data = set_to_str([s.email for s in exam.students])
    return render_template('email.html.j2', exam=exam, form=form)


@app.route('/<exam:exam>/students/email/<string:student_id>/', methods=['GET', 'POST'])
def email_single_student(exam, student_id):
    form = EmailForm()
    if form.validate_on_submit():
        successful_emails, failed_emails = email_about_assignment(exam, form, form.to_addr.data)
        if successful_emails:
            flash(f"Successfully emailed {len(successful_emails)} students.", 'success')
        if failed_emails:
            flash(f"Failed to email students: {set_to_str(failed_emails)}", 'error')
        if not successful_emails and not failed_emails:
            flash("No email sent.", 'warning')
        return redirect(url_for('students', exam=exam))
    else:
        student = Student.query.get_or_404(student_id)
        email_prefill = get_email(EmailTemplate.ASSIGNMENT_INFORM_EMAIL)
        form.subject.data = email_prefill.subject
        form.body.data = email_prefill.body
        subject, body = substitute_about_assignment(exam, form, student)
        form.subject.data = subject
        form.body.data = body
        form.to_addr.data = student.email
    return render_template('email.html.j2', exam=exam, form=form)


@app.route('/<exam_student:exam_student>', methods=['GET'])
def student(exam_student):
    exam, student = exam_student
    return render_template('student.html.j2', exam=exam, student=student)


@app.route('/<exam_student:exam_student>/photo/', methods=['GET'])
def student_photo(exam_student):
    _, student = exam_student
    sid = student.sid
    if sid:
        from server.cache import cache_store, cache_key_photo, cache_life_photo
        import io
        photo = cache_store.get(cache_key_photo(sid))
        if photo is not None:
            return send_file(io.BytesIO(photo), mimetype='image/jpeg')
        from server.services.c1c import c1c_client
        photo = c1c_client.get_student_photo(sid)
        if photo is not None:
            cache_store.set(cache_key_photo(sid), photo, timeout=cache_life_photo)
            return send_file(io.BytesIO(photo), mimetype='image/jpeg')
    return send_file('static/img/photo-placeholder.png', mimetype='image/png')

# endregion

# region Misc


@app.context_processor
def inject_env_vars():
    return dict(wiki_base_url=app.config.get('WIKI_BASE_URL'))


@app.route('/favicon.ico')
def favicon():
    return send_file('static/img/favicon.ico')


@app.route('/students-template.png')
def students_template():
    return send_file('static/img/students-template.png')
# endregion

# region Student-facing pages


@app.route('/seats/<int:seat_id>/')
def student_single_seat(seat_id):
    seat = Seat.query.filter_by(id=seat_id).first_or_404()
    return render_template('seat.html.j2', room=seat.room, seat=seat)
# endregion
