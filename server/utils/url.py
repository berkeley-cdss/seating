from logging import config
from flask import abort, redirect, request, session, url_for
from flask_login import current_user
from werkzeug.exceptions import HTTPException
from werkzeug.routing import BaseConverter
import server.utils.canvas as canvas_client

from server import app
from server.models import db, Offering, Exam


class Redirect(HTTPException):
    code = 302

    def __init__(self, url):
        self.url = url

    def get_response(self, environ=None):
        return redirect(self.url)


ban_words = '(?!(((new)|(offerings)|(exams))\b))'
offering_regex = ban_words + r'\d+'
exam_regex = ban_words + r'\w+'


def format_exam_url(offering_canvas_id, exam_name):
    return 'offerings/{}/exams/{}'.format(offering_canvas_id, exam_name)


class ExamConverter(BaseConverter):
    regex = format_exam_url(offering_regex, exam_regex)

    def to_python(self, value):
        if not current_user.is_authenticated:
            session['after_login'] = request.url
            raise Redirect(url_for('login'))
        _, canvas_id, _, exam_name = value.split('/', 3)
        if str(canvas_id) not in current_user.staffing:
            abort(403, "You are not a staff member in this offering.")
        exam = Exam.query.filter_by(
            offering_canvas_id=canvas_id, name=exam_name
        ).first_or_404()
        return exam

    def to_url(self, exam):
        return format_exam_url(exam.offering_canvas_id, exam.name)


def format_offering_url(canvas_id):
    return "offerings/{}".format(canvas_id)


class OfferingConverter(BaseConverter):
    regex = format_offering_url(offering_regex)

    def to_python(self, value):
        if not current_user.is_authenticated:
            session['after_login'] = request.url
            raise Redirect(url_for('login'))
        canvas_id = value.rsplit('/', 1)[-1]
        if str(canvas_id) not in current_user.staffing:
            abort(403, "You are not a staff member in this offering.")
        offering = Offering.query.filter_by(
            canvas_id=canvas_id).one_or_none()
        if not offering:
            course_raw = canvas_client.get_course(canvas_id)
            if not course_raw:
                abort(404, "Offering not found from Canvas.")
            offering = Offering(
                canvas_id=canvas_id,
                name=course_raw['name'],
                code=course_raw['course_code'])
            db.session.add(offering)
            db.session.commit()
        return offering

    def to_url(self, offering):
        return format_offering_url(offering.canvas_id)


def apply_converter():
    app.url_map.converters['exam'] = ExamConverter
    app.url_map.converters['offering'] = OfferingConverter
