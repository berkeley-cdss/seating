/*
 * Client side behaviour for the seating layout preview page.
 *
 * The server renders every seat of the uploaded file as a button carrying its
 * own data (name, coordinates, attributes), plus a JSON blob describing the
 * canonical seat-attribute vocabulary. Everything after that -- highlighting a
 * layout, toggling seats and their attributes, and exporting the result back to
 * CSV -- happens here, so nothing is ever written to the database.
 */
(function () {
  'use strict';

  /* Sample CSV helper on the upload form. */
  function initSampleButton() {
    var loadSample = document.getElementById('layout-load-sample');
    if (!loadSample) {
      return;
    }
    loadSample.addEventListener('click', function () {
      var sample = document.getElementById('layout-sample-csv');
      var textarea = document.getElementById('layout-csv-text');
      if (!sample || !textarea) {
        return;
      }
      textarea.value = sample.textContent.trim() + '\n';
      // The example lands in the paste box, so bring that tab forward.
      var tab = document.querySelector('.mdl-tabs__tab[href="#preview-paste-panel"]');
      if (tab) {
        tab.click();
      }
      textarea.focus();
    });
  }

  function initEditor() {
    var root = document.getElementById('layout-preview');
    var payload = document.getElementById('layout-data');
    if (!root || !payload) {
      return;
    }

    // Only the seat chart's buttons; the legend's swatches share the seat's
    // look (and its class) but are spans, and belong to no layout.
    var seats = Array.prototype.slice.call(root.querySelectorAll('button.layout-seat'));
    var modeToggle = document.getElementById('layout-mode-toggle');
    if (!seats.length || !modeToggle) {
      return;
    }

    var data = JSON.parse(payload.textContent);
    var vocabulary = data.vocabulary || [];
    var columns = data.columns || [];
    var byKey = {};
    vocabulary.forEach(function (item) {
      byKey[item.key] = item;
    });

    var highlight = document.getElementById('layout-highlight');
    var detail = document.getElementById('layout-detail');
    var selectedCount = document.getElementById('layout-selected-count');
    var layoutName = document.getElementById('layout-name');
    var columnPreview = document.getElementById('layout-column-preview');
    var brokenCount = document.getElementById('layout-broken-count');
    var editControls = Array.prototype.slice.call(root.querySelectorAll('.layout-edit-only'));
    var editing = false;

    /* ---------------------------------------------------------------- *
     * Seat state
     * ---------------------------------------------------------------- */

    function isSelected(seat) {
      return seat.getAttribute('data-selected') === 'true';
    }

    function setSelected(seat, selected) {
      seat.setAttribute('data-selected', selected ? 'true' : 'false');
      seat.setAttribute('aria-pressed', selected ? 'true' : 'false');
    }

    function attributesOf(seat) {
      var raw = seat.getAttribute('data-attributes') || '';
      return raw ? raw.split(',') : [];
    }

    function knownAttributesOf(seat) {
      return attributesOf(seat).filter(function (key) {
        return byKey[key];
      });
    }

    /* Redraw a seat from its attributes: the slash, the L/R letter, the
     * marker dot and the hover text all follow from them. */
    function refreshSeat(seat) {
      var known = knownAttributesOf(seat);
      var broken = known.some(function (key) {
        return byKey[key].broken;
      });
      // Mirrors seat_badge() on the server: only a seat that works left-handed
      // and nothing else is labelled, since righty is the default everywhere
      // and a letter on every seat drowns out the layout itself.
      var badge = (!broken && known.indexOf('lefty') !== -1 &&
                   known.indexOf('righty') === -1) ? 'L' : '';
      var notes = known.some(function (key) {
        return byKey[key].note;
      });
      var labels = known.map(function (key) {
        return byKey[key].label;
      }).sort();
      var name = seat.getAttribute('data-name') || 'Movable seat';
      var label = labels.length ? name + ' — ' + labels.join(', ') : name;

      seat.setAttribute('data-broken', broken ? 'true' : 'false');
      seat.setAttribute('data-notes', notes ? 'true' : 'false');
      seat.setAttribute('data-badge', badge);
      seat.setAttribute('data-label', label);
      seat.setAttribute('aria-label', label);
      seat.querySelector('.layout-seat__badge').textContent = badge;

      var tooltip = root.querySelector('.seat-tooltip[for="' + seat.id + '"]');
      if (tooltip) {
        tooltip.innerHTML = '';
        tooltip.appendChild(document.createTextNode(name));
        labels.forEach(function (text) {
          tooltip.appendChild(document.createElement('br'));
          tooltip.appendChild(document.createTextNode(text));
        });
      }
    }

    function setAttribute(seat, key, on) {
      var attributes = attributesOf(seat).filter(function (existing) {
        return existing !== key;
      });
      if (on) {
        attributes.push(key);
      }
      attributes.sort();
      seat.setAttribute('data-attributes', attributes.join(','));
      refreshSeat(seat);
      refreshCounts();
    }

    /* ---------------------------------------------------------------- *
     * Counts and status line
     * ---------------------------------------------------------------- */

    function refreshCounts() {
      selectedCount.textContent = seats.filter(isSelected).length;
      if (brokenCount) {
        brokenCount.textContent = seats.filter(function (seat) {
          return seat.getAttribute('data-broken') === 'true';
        }).length;
      }
      // The legend counts describe the seats as they stand, edits included.
      var tallies = {};
      seats.forEach(function (seat) {
        attributesOf(seat).forEach(function (key) {
          tallies[key] = (tallies[key] || 0) + 1;
        });
      });
      Array.prototype.forEach.call(root.querySelectorAll('[data-legend-count]'), function (el) {
        el.textContent = tallies[el.getAttribute('data-legend-count')] || 0;
      });
    }

    function describe(text) {
      if (detail) {
        detail.textContent = text;
      }
    }

    function describeSeat(seat) {
      describe(seat.getAttribute('data-label') + ' — ' +
        (isSelected(seat) ? 'In layout' : 'Not in layout'));
    }

    /* ---------------------------------------------------------------- *
     * Modes
     * ---------------------------------------------------------------- */

    function applyHighlight() {
      var key = highlight ? highlight.value : '';
      seats.forEach(function (seat) {
        setSelected(seat, !key || attributesOf(seat).indexOf(key) !== -1);
      });
      refreshCounts();
    }

    function setEditing(next) {
      editing = next;
      root.classList.toggle('layout-preview__editing', editing);
      modeToggle.setAttribute('aria-pressed', editing ? 'true' : 'false');
      modeToggle.textContent = editing ? 'Done editing' : 'New layout';
      editControls.forEach(function (el) {
        el.hidden = !editing;
      });
      seats.forEach(function (seat) {
        if (editing) {
          seat.removeAttribute('aria-disabled');
        } else {
          seat.setAttribute('aria-disabled', 'true');
        }
      });
      closeMenu();
      if (editing) {
        // A new layout starts from the whole room, then gets narrowed down.
        if (highlight) {
          highlight.value = '';
        }
        seats.forEach(function (seat) {
          setSelected(seat, true);
        });
        refreshCounts();
        describe('Every seat starts in the layout. Click a seat to remove it, ' +
          'or right-click it to change its attributes.');
        if (layoutName) {
          layoutName.focus();
          layoutName.select();
        }
      } else {
        describe('Use the dropdown to highlight the seats in a layout.');
      }
    }

    /* ---------------------------------------------------------------- *
     * Per-seat attribute menu
     * ---------------------------------------------------------------- */

    var menu = document.createElement('div');
    menu.className = 'layout-menu mdl-shadow--4dp';
    menu.hidden = true;
    menu.innerHTML = '<div class="layout-menu__title"></div><div class="layout-menu__body"></div>';
    document.body.appendChild(menu);
    var menuTitle = menu.querySelector('.layout-menu__title');
    var menuBody = menu.querySelector('.layout-menu__body');

    function closeMenu() {
      menu.hidden = true;
    }

    function checkboxRow(labelText, checked, onChange) {
      var row = document.createElement('label');
      row.className = 'layout-menu__item';
      var box = document.createElement('input');
      box.type = 'checkbox';
      box.checked = checked;
      box.addEventListener('change', function () {
        onChange(box.checked);
      });
      row.appendChild(box);
      row.appendChild(document.createTextNode(labelText));
      return row;
    }

    function openMenu(seat, x, y) {
      menuTitle.textContent = seat.getAttribute('data-name') || 'Movable seat';
      menuBody.innerHTML = '';

      menuBody.appendChild(checkboxRow('In this layout', isSelected(seat), function (on) {
        setSelected(seat, on);
        refreshCounts();
        describeSeat(seat);
      }));

      var group = null;
      vocabulary.forEach(function (item) {
        if (item.group !== group) {
          group = item.group;
          var heading = document.createElement('div');
          heading.className = 'layout-menu__group';
          heading.textContent = group;
          menuBody.appendChild(heading);
        }
        var on = attributesOf(seat).indexOf(item.key) !== -1;
        menuBody.appendChild(checkboxRow(item.label, on, function (checked) {
          setAttribute(seat, item.key, checked);
          describeSeat(seat);
        }));
      });

      menu.hidden = false;
      // Keep the menu on screen even when a seat is near an edge.
      var width = menu.offsetWidth;
      var height = menu.offsetHeight;
      var left = Math.min(x, window.pageXOffset + document.documentElement.clientWidth - width - 8);
      var top = Math.min(y, window.pageYOffset + document.documentElement.clientHeight - height - 8);
      menu.style.left = Math.max(8, left) + 'px';
      menu.style.top = Math.max(8, top) + 'px';
    }

    document.addEventListener('click', function (event) {
      if (!menu.hidden && !menu.contains(event.target)) {
        closeMenu();
      }
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        closeMenu();
      }
    });

    /* ---------------------------------------------------------------- *
     * Wiring
     * ---------------------------------------------------------------- */

    seats.forEach(function (seat) {
      seat.addEventListener('click', function () {
        if (!editing) {
          return;
        }
        setSelected(seat, !isSelected(seat));
        refreshCounts();
        describeSeat(seat);
      });
      // Fires for the right mouse button and for the keyboard's menu key.
      seat.addEventListener('contextmenu', function (event) {
        if (!editing) {
          return;
        }
        event.preventDefault();
        var box = seat.getBoundingClientRect();
        var x = event.pageX || (box.left + window.pageXOffset);
        var y = event.pageY || (box.bottom + window.pageYOffset);
        openMenu(seat, x, y);
      });
      seat.addEventListener('mouseenter', function () {
        describeSeat(seat);
      });
      seat.addEventListener('focus', function () {
        describeSeat(seat);
      });
    });

    if (highlight) {
      highlight.addEventListener('change', applyHighlight);
    }

    modeToggle.addEventListener('click', function () {
      setEditing(!editing);
    });

    function bind(id, handler) {
      var el = document.getElementById(id);
      if (el) {
        el.addEventListener('click', handler);
      }
    }

    bind('layout-select-all', function () {
      seats.forEach(function (seat) {
        setSelected(seat, true);
      });
      refreshCounts();
    });

    bind('layout-select-none', function () {
      seats.forEach(function (seat) {
        setSelected(seat, false);
      });
      refreshCounts();
    });

    bind('layout-invert', function () {
      seats.forEach(function (seat) {
        setSelected(seat, !isSelected(seat));
      });
      refreshCounts();
    });

    bind('layout-drop-broken', function () {
      seats.forEach(function (seat) {
        if (seat.getAttribute('data-broken') === 'true') {
          setSelected(seat, false);
        }
      });
      refreshCounts();
    });

    bind('layout-export', function () {
      download(buildCsv(), fileName());
    });

    if (layoutName) {
      layoutName.addEventListener('input', function () {
        if (columnPreview) {
          columnPreview.textContent = columnName();
        }
      });
    }

    /* ---------------------------------------------------------------- *
     * Export: the same file back out, plus a column for the new layout
     * ---------------------------------------------------------------- */

    // Column names are lowercased on import and are otherwise free-form, so
    // keep the name the user typed and only drop what would break a CSV cell.
    function columnName() {
      var raw = layoutName ? layoutName.value : '';
      return raw.toLowerCase().replace(/["',\r\n]+/g, ' ').trim().replace(/\s+/g, ' ') || 'newlayout';
    }

    function fileName() {
      return columnName().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') + '.csv';
    }

    var RESERVED_COLUMNS = ['row', 'seat', 'x', 'y', 'count'];

    /* The file's own columns first, in their original order, then anything
     * added while editing. */
    function flagColumns(exclude) {
      var seen = {};
      var ordered = [];
      function add(key) {
        if (key && !seen[key] && RESERVED_COLUMNS.indexOf(key) === -1 && key !== exclude) {
          seen[key] = true;
          ordered.push(key);
        }
      }
      columns.forEach(add);
      seats.forEach(function (seat) {
        attributesOf(seat).forEach(add);
      });
      return ordered;
    }

    function escapeCell(value) {
      var text = value === null || value === undefined ? '' : String(value);
      return /[",\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
    }

    function buildCsv() {
      var column = columnName();
      var flags = flagColumns(column);
      var movable = seats.filter(function (seat) {
        return seat.getAttribute('data-fixed') !== 'true';
      });

      var headers = ['row', 'seat', 'x', 'y'];
      if (movable.length) {
        headers.push('count');
      }
      headers = headers.concat(flags, [column]);

      var lines = [headers.map(escapeCell).join(',')];

      function makeRow(values) {
        return headers.map(function (header) {
          return escapeCell(values[header]);
        }).join(',');
      }

      seats.filter(function (seat) {
        return seat.getAttribute('data-fixed') === 'true';
      }).forEach(function (seat) {
        var values = {
          row: seat.getAttribute('data-row'),
          seat: seat.getAttribute('data-seat-num'),
          x: seat.getAttribute('data-x'),
          y: seat.getAttribute('data-y')
        };
        var own = attributesOf(seat);
        flags.forEach(function (key) {
          values[key] = own.indexOf(key) !== -1 ? 'TRUE' : '';
        });
        values[column] = isSelected(seat) ? 'TRUE' : '';
        lines.push(makeRow(values));
      });

      // Movable seats have no coordinates, so they collapse back into one
      // counted row per (attributes, in-layout) combination.
      var groups = {};
      movable.forEach(function (seat) {
        var key = attributesOf(seat).join(',') + '|' + isSelected(seat);
        if (!groups[key]) {
          groups[key] = { attributes: attributesOf(seat), selected: isSelected(seat), count: 0 };
        }
        groups[key].count += 1;
      });
      Object.keys(groups).sort().forEach(function (key) {
        var group = groups[key];
        var values = { row: '', seat: '', x: '', y: '', count: group.count };
        flags.forEach(function (flag) {
          values[flag] = group.attributes.indexOf(flag) !== -1 ? 'TRUE' : '';
        });
        values[column] = group.selected ? 'TRUE' : '';
        lines.push(makeRow(values));
      });

      return lines.join('\n') + '\n';
    }

    function download(text, filename) {
      var blob = new Blob([text], { type: 'text/csv;charset=utf-8;' });
      var url = URL.createObjectURL(blob);
      var link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    }

    setEditing(false);
    refreshCounts();
  }

  function init() {
    initSampleButton();
    initEditor();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
