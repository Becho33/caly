document.addEventListener('DOMContentLoaded', function () {

    console.log('[calendar] calaendar.js loaded');

    var calendarEl = document.getElementById('calendar');

    // helper to show booking modal from an event object
    function showBookingModal(ev) {
        console.log('[calendar] showBookingModal', ev && ev.id);
        var props = ev.extendedProps || {};

        var setText = function(id, value) {
            var el = document.getElementById(id);
            if (el) el.textContent = value;
        };

        setText('bd-customer', ev.title || '-');
        setText('bd-phone', props.phone || '-');
        setText('bd-room', props.room || '-');
        setText('bd-location', props.location || '-');
        setText('bd-start', ev.start ? ev.start.toLocaleString() : '-');
        setText('bd-end', ev.end ? ev.end.toLocaleString() : '-');
        setText('bd-duration', props.duration ? props.duration + ' mins' : '-');
        setText('bd-paid', (props.paid === true || props.paid === 'true') ? 'Yes' : 'No');

        var editLink = document.getElementById('bd-edit-link');
        if (editLink) {
            if (ev.id) {
                editLink.setAttribute('href', '/edit-booking/' + ev.id);
                editLink.style.display = 'inline-block';
            } else {
                editLink.style.display = 'none';
            }
        }

        // set delete button data-id
        var deleteBtn = document.getElementById('bd-delete-btn');
        if (deleteBtn) {
            if (ev.id) {
                deleteBtn.dataset.id = ev.id;
                deleteBtn.style.display = 'inline-block';
            } else {
                deleteBtn.style.display = 'none';
            }
        }

        var bookingModalEl = document.getElementById('bookingDetailsModal');
        if (!bookingModalEl) {
            console.error('[calendar] Modal element missing');
            return;
        }
        var bookingModal = new bootstrap.Modal(bookingModalEl);
        bookingModal.show();
    }

    // helper: map therapist/room names to fixed colors
    function getColorForRoom(name) {
        var map = {
            'Jules': '#FF6B6B',
            'Aly': '#6BCB77',
            'Amira': '#4D96FF',
            'Echo': '#FFD93D',
            'Suprani': '#845EC2',
            'Rose': '#FF9CEE',
            'Daisy': '#FFA15C',
            'Lay': '#00C9A7',
            'Not assigned yet': '#9E9E9E'
        };
        return map[name] || '#777777';
    }

    // expose calendar variable to outer scope for refetching after delete
    window._bookingCalendar = new FullCalendar.Calendar(calendarEl, {

        initialView: 'dayGridMonth',

        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,timeGridWeek,timeGridDay'
        },

        events: '/events',

        selectable: true,
        editable: true,

        // When user clicks a date
        dateClick: function(info) {
            console.log('[calendar] dateClick', info.dateStr);
            // small UX: navigate to add booking with date? currently alert
            // alert("You clicked on: " + info.dateStr);
        },

        // When user clicks an event
        eventClick: function(info) {
            console.log('[calendar] eventClick', info.event && info.event.id);
            showBookingModal(info.event);
        },

        // style events by therapist/room name
        eventDidMount: function(info) {
            var room = info.event.extendedProps.room || '';
            info.el.style.backgroundColor = getColorForRoom(room);
            info.el.style.color = '#ffffff';
            info.el.style.border = info.event.extendedProps.paid === false ? '2px solid red' : '1px solid #333';

            // make event element explicitly clickable and attach fallback click
            try {
                info.el.style.cursor = 'pointer';
                info.el.addEventListener('click', function(e) {
                    // prevent double-handling if FullCalendar also fires eventClick
                    e.stopPropagation();
                    showBookingModal(info.event);
                });
            } catch (err) {
                console.warn('[calendar] could not attach fallback click to event element', err);
            }
        }

    });

    window._bookingCalendar.render();

    // delete booking handler
    var deleteBtn = document.getElementById('bd-delete-btn');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', function() {
            var id = this.dataset.id;
            if (!id) return;

            if (!confirm('Delete this booking? This cannot be undone.')) return;

            fetch('/delete-booking/' + id, { method: 'DELETE' })
                .then(function(res) { return res.json(); })
                .then(function(json) {
                    if (json.success) {
                        // close modal
                        var bookingModalEl = document.getElementById('bookingDetailsModal');
                        var m = bootstrap.Modal.getInstance(bookingModalEl);
                        if (m) m.hide();

                        // refresh calendar
                        if (window._bookingCalendar) window._bookingCalendar.refetchEvents();
                        alert('Booking deleted');
                    } else {
                        alert('Could not delete booking');
                    }
                }).catch(function(err) {
                    console.error('delete error', err);
                    alert('Delete failed');
                });
        });
    }

});