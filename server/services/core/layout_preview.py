"""
Display semantics for the standalone seating layout preview.

Every column of a room spreadsheet other than row/seat/x/y/count arrives as a
lowercase boolean flag, and the schema draws no distinction between two very
different kinds of flag:

* a **seat attribute** - a physical property of the chair, true no matter which
  exam is being seated ("lefty", "broken", "aisle");
* a **layout** - a named selection of seats to use for one exam or room setup
  ("alternateseating1", "2/3 seating", "2050vlsb", "cs61c_sp26_alt3").

Because a layout can be called anything, name matching cannot tell the two
apart reliably. So this module inverts the question: SEAT_ATTRIBUTES below is
the canonical, closed vocabulary of seat attributes, and **every other column
is a layout**. Adding a new attribute to the vocabulary is a one line change
here; nothing else needs to know about it.
"""

import itertools
import re
from dataclasses import dataclass

from natsort import natsorted

LAYOUT_GROUP = 'Layouts'
HANDEDNESS_GROUP = 'Handedness'
CONDITION_GROUP = 'Condition'
PLACEMENT_GROUP = 'Placement & Use'

# The order groups appear in the highlight dropdown and the legend.
ATTRIBUTE_GROUPS = [HANDEDNESS_GROUP, CONDITION_GROUP, PLACEMENT_GROUP]
GROUP_ORDER = [LAYOUT_GROUP] + ATTRIBUTE_GROUPS

# The canonical seat attributes: (label, group, badge, description).
# Keys are the lowercased spreadsheet column names. Anything not in here is
# treated as a layout, so keep this list in sync with the master room sheet.
SEAT_ATTRIBUTES = {
    'lefty': ('Lefty', HANDEDNESS_GROUP, 'L', 'Has a left-handed desk or writing surface.'),
    'righty': ('Righty', HANDEDNESS_GROUP, '', 'Has a right-handed desk or writing surface.'),
    'broken': ('Broken', CONDITION_GROUP, '', 'Broken, and cannot be assigned.'),
    'damaged': ('Damaged', CONDITION_GROUP, '', 'Damaged, and cannot be assigned.'),
    'unusable': ('Unusable', CONDITION_GROUP, '', 'Cannot be assigned, for any reason.'),
    'aisle': ('Aisle', PLACEMENT_GROUP, '', 'Directly next to an aisle.'),
    'front': ('Front', PLACEMENT_GROUP, '', 'Near the front of the room.'),
    'back': ('Back', PLACEMENT_GROUP, '', 'Near the back of the room.'),
    'center': ('Center', PLACEMENT_GROUP, '', 'In the middle section of the room.'),
    'corner': ('Corner', PLACEMENT_GROUP, '', 'In a corner of the room.'),
    'window': ('Window', PLACEMENT_GROUP, '', 'Next to a window.'),
    'table': ('Table', PLACEMENT_GROUP, '', 'At a table rather than a fold-out desk.'),
    'power': ('Power', PLACEMENT_GROUP, '', 'Has a power outlet within reach.'),
    'walkingrow': ('Walking Row', PLACEMENT_GROUP, '', 'In a row kept clear for proctors.'),
    'movable': ('Movable', PLACEMENT_GROUP, '', 'Can be moved around the room.'),
    'reserved': ('Reserved', PLACEMENT_GROUP, '', 'Held back for a specific purpose.'),
    'restricted': ('Restricted', PLACEMENT_GROUP, '', 'Only usable under some restriction.'),
    'dsp': ('DSP', PLACEMENT_GROUP, '', 'Kept for students with DSP accommodations.'),
}

# Attributes whose presence makes a seat unusable. Drawn with a red background
# and a slash, and never labelled with a handedness letter.
BROKEN_KEYS = frozenset(
    key for key, (_, group, _, _) in SEAT_ATTRIBUTES.items() if group == CONDITION_GROUP)

# Attributes that limit who may sit in a seat. These get a marker dot on the
# chart; the purely positional ones (aisle, front, table, ...) do not, because
# whole rooms are tagged with them and a dot on every seat says nothing.
NOTABLE_KEYS = frozenset({'dsp', 'reserved', 'restricted', 'walkingrow', 'movable'})


@dataclass(frozen=True)
class AttributeInfo:
    """How a single spreadsheet column should be presented to a user."""
    key: str
    label: str
    group: str
    badge: str
    description: str

    @property
    def is_layout(self):
        return self.group == LAYOUT_GROUP

    @property
    def is_broken(self):
        return self.key in BROKEN_KEYS

    @property
    def is_notable(self):
        """Worth a marker on the seat itself, rather than only on hover."""
        return self.key in NOTABLE_KEYS


def normalize_attribute(attribute):
    return str(attribute).strip().lower()


def describe_attribute(attribute, display_name=None):
    """
    Return the display semantics of a single column.

    Columns outside the canonical vocabulary are layouts. A layout is named by
    whoever made the spreadsheet, so it is labelled with its own column heading,
    spelled the way the file spells it.
    """
    key = normalize_attribute(attribute)
    known = SEAT_ATTRIBUTES.get(key)
    if known:
        label, group, badge, description = known
        return AttributeInfo(key=key, label=label, group=group, badge=badge, description=description)
    return AttributeInfo(key=key, label=(display_name or _layout_label(key)), group=LAYOUT_GROUP,
                         badge='', description='A named set of seats defined by this file.')


def _layout_label(key):
    """Make a layout column name readable when the original heading is gone."""
    label = re.sub(r'(alternate)(seating)', r'\1 \2', key)
    label = re.sub(r'(?<=[a-z])(\d)', r' \1', label)
    label = label.replace('_', ' ').replace('-', ' ')
    return ' '.join(word if word.isupper() else word.title() for word in label.split())


def describe_attributes(attributes, names=None):
    """
    Describe a collection of columns, ordered by group then label.

    `names` maps a lowercased column key back to its original heading.
    """
    names = names or {}
    infos = {describe_attribute(a, names.get(normalize_attribute(a))) for a in attributes}
    return sorted(infos, key=lambda i: (GROUP_ORDER.index(i.group), i.label))


def seat_attribute_vocabulary():
    """
    The canonical seat attributes, for the seat editor's toggle menu.

    Each entry carries everything the client needs to redraw a seat after an
    attribute is toggled, so the rendering rules live in one place.
    """
    return [{'key': info.key, 'label': info.label, 'group': info.group,
             'description': info.description, 'badge': info.badge,
             'broken': info.is_broken, 'note': info.is_notable}
            for info in describe_attributes(SEAT_ATTRIBUTES)]


def is_broken(attributes):
    return any(normalize_attribute(a) in BROKEN_KEYS for a in attributes)


def seat_badge(attributes):
    """
    The letter drawn on a seat: "L" for a seat that only works left-handed.

    Righty is the default desk in every room of the master sheet - a couple of
    hundred "R"s is noise, not information - so only the exceptions are
    labelled. A desk tagged both ways constrains nobody, and a broken seat
    already carries a slash, so neither gets a letter.
    """
    keys = {normalize_attribute(a) for a in attributes}
    if is_broken(keys):
        return ''
    return 'L' if 'lefty' in keys and 'righty' not in keys else ''


def seat_label(seat_name, attributes):
    """A human readable one-liner for a seat, used as its accessible name."""
    infos = [info for info in describe_attributes(attributes) if not info.is_layout]
    label = seat_name or 'Movable seat'
    if infos:
        label += ' — ' + ', '.join(info.label for info in infos)
    return label


def _seat_to_dict(seat, index):
    attributes = sorted(normalize_attribute(a) for a in seat.attributes)
    infos = describe_attributes(attributes)
    return {
        'id': f'preview-seat-{index}',
        'name': seat.name or '',
        'row': seat.row or '',
        'seat': seat.seat or '',
        'x': seat.x,
        'y': seat.y,
        'fixed': bool(seat.fixed),
        'attributes': attributes,
        'badge': seat_badge(attributes),
        'broken': is_broken(attributes),
        'label': seat_label(seat.name, attributes),
        # Only seat attributes are worth showing on hover; which layouts a seat
        # belongs to is what the highlight dropdown is for.
        'attribute_labels': [info.label for info in infos if not info.is_layout],
        # Attributes that restrict who may use the seat get a marker dot.
        'notes': [info.label for info in infos if info.is_notable],
    }


def _grid_rows(fixed_seats):
    """Group fixed seats into display rows, matching how a Room renders them."""
    ordered = natsorted(fixed_seats, key=lambda s: s['row'])
    return [natsorted(group, key=lambda s: s['x'])
            for _, group in itertools.groupby(ordered, key=lambda s: s['row'])]


def _movable_groups(movable_seats, names):
    """Group movable seats by their attribute set, since they have no coordinates."""
    groups = {}
    for seat in movable_seats:
        groups.setdefault(tuple(seat['attributes']), []).append(seat)
    return [{
        'attributes': list(attributes),
        'label': ', '.join(info.label for info in describe_attributes(attributes, names)) or 'No attributes',
        'seats': seats,
    } for attributes, seats in sorted(groups.items())]


def _attribute_counts(seat_dicts):
    """How many seats carry each column present in this file."""
    counts = {}
    for seat in seat_dicts:
        for key in seat['attributes']:
            counts[key] = counts.get(key, 0) + 1
    return counts


def _grouped(counts, names):
    """Columns present in this file, grouped and ordered for display."""
    return [(group, list(infos)) for group, infos in itertools.groupby(
        describe_attributes(counts, names), key=lambda info: info.group)]


def build_layout_preview(seats, columns=None):
    """
    Turn a list of (unsaved) Seat objects into everything the preview page and
    its client-side editor need to render, filter, edit and export a layout.

    `columns` is the header row the seats came from, so that an exported layout
    can keep the file's own column order.
    """
    seat_dicts = [_seat_to_dict(seat, index) for index, seat in enumerate(seats)]
    fixed = [s for s in seat_dicts if s['fixed']]
    movable = [s for s in seat_dicts if not s['fixed']]
    counts = _attribute_counts(seat_dicts)
    # Layouts are labelled with their heading as the spreadsheet spells it.
    names = {normalize_attribute(c): str(c).strip() for c in (columns or [])}
    grouped = _grouped(counts, names)

    bounds = None
    if fixed:
        xs = [s['x'] for s in fixed]
        ys = [s['y'] for s in fixed]
        bounds = {'x_min': min(xs), 'x_max': max(xs), 'y_min': min(ys), 'y_max': max(ys)}

    def entries(infos):
        return [{'key': info.key, 'label': info.label, 'badge': info.badge,
                 'broken': info.is_broken, 'note': info.is_notable,
                 'description': info.description, 'count': counts[info.key]}
                for info in infos]

    return {
        'seats': seat_dicts,
        'fixed_seats': fixed,
        'movable_seats': movable,
        'grid_rows': _grid_rows(fixed),
        'movable_groups': _movable_groups(movable, names),
        'bounds': bounds,
        # One <optgroup> per family in the highlight dropdown, layouts first.
        'highlight_options': [{
            'group': group,
            'options': [{'key': info.key, 'label': info.label, 'count': counts[info.key]}
                        for info in infos],
        } for group, infos in grouped],
        # The legend splits the file's columns the same way the schema does.
        'legend_layouts': [entry for group, infos in grouped if group == LAYOUT_GROUP
                           for entry in entries(infos)],
        'legend_attributes': [{'group': group, 'entries': entries(infos)}
                              for group, infos in grouped if group != LAYOUT_GROUP],
        'vocabulary': seat_attribute_vocabulary(),
        'columns': [normalize_attribute(c) for c in (columns or [])],
        'counts': {
            'total': len(seat_dicts),
            'fixed': len(fixed),
            'movable': len(movable),
            'broken': sum(1 for s in seat_dicts if s['broken']),
        },
    }
