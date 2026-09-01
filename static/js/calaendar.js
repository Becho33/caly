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

        setText('bd-customer', props.customer_name || ev.title || '-');
        setText('bd-phone', props.phone || '-');
        setText('bd-staff', props.staff || 'Not assigned yet');
        setText('bd-location', props.location || '-');
        setText('bd-start', ev.start ? ev.start.toLocaleString() : '-');
        setText('bd-end', ev.end ? ev.end.toLocaleString() : '-');
        setText('bd-duration', props.duration ? props.duration + ' mins' : '-');
        var paymentLabels = { paid: 'Paid', not_paid: 'Not Paid', group: 'Groupon Voucher' };
        setText('bd-paid', paymentLabels[props.payment_status] || ((props.paid === true || props.paid === 'true') ? 'Paid' : 'Not Paid'));

        var editLink = document.getElementById('bd-edit-link');
        if (editLink) {
            if (ev.id) {
                editLink.setAttribute('href', '/edit-booking/' + ev.id);
                editLink.style.display = 'inline-block';
            } else {
                editLink.style.display = 'none';
            }
        }

        var revealLink = document.getElementById('bd-reveal-link');
        if (revealLink && ev.id) {
            revealLink.setAttribute('href', '/privacy/unlock?next=' + encodeURIComponent('/calendar?booking=' + ev.id));
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
        var bookingModal = bootstrap.Modal.getOrCreateInstance(bookingModalEl);
        bookingModal.show();
    }

    // helper: map staff names to fixed colors
    function getColorForStaff(name) {
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
        // There is no server endpoint for persisting drag/drop changes.
        editable: false,

        // When user clicks a date
        dateClick: function(info) {
            window.location.href = '/add-booking?date=' + encodeURIComponent(info.dateStr.substring(0, 10));
        },

        // When user clicks an event
        eventClick: function(info) {
            console.log('[calendar] eventClick', info.event && info.event.id);
            showBookingModal(info.event);
        },

        // style events by assigned staff member
        eventDidMount: function(info) {
            var staff = info.event.extendedProps.staff || 'Not assigned yet';
            info.el.style.backgroundColor = getColorForStaff(staff);
            info.el.style.color = '#ffffff';
            info.el.style.border = info.event.extendedProps.paid === false ? '2px solid red' : '1px solid #333';

            info.el.style.cursor = 'pointer';
        },

        eventsSet: function() {
            var bookingId = new URLSearchParams(window.location.search).get('booking');
            if (!bookingId || window._reopenedBooking) return;
            var event = window._bookingCalendar.getEventById(bookingId);
            if (event) {
                window._reopenedBooking = true;
                showBookingModal(event);
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
                        var status = document.getElementById('calendar-status');
                        if (status) status.textContent = 'Booking deleted successfully.';
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
