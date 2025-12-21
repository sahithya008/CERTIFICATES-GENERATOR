import io
import os
import sys
import pytest
# Ensure the project root is on PYTHONPATH so tests can import the app module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app, is_cert_eligible, db, CertificateDownload, students


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def test_home_loads(client):
    rv = client.get('/')
    assert rv.status_code == 200
    assert b'Certificate Generator' in rv.data


def test_is_cert_eligible():
    assert is_cert_eligible("Bonafide", "STUDYING", "") is True
    assert is_cert_eligible("Course Completion", "STUDYING", "") is False
    assert is_cert_eligible("Custodium", "COMPLETED", "some") is False


def test_check_status_invalid(client):
    rv = client.get('/check_status/INVALID123')
    assert rv.status_code == 200
    assert b'invalid' in rv.data


def test_payment_missing_fields_redirect(client):
    rv = client.post('/payment', data={})
    # Should redirect to home because required fields are missing
    assert rv.status_code == 302


def test_verify_payment_upload_flow(client, tmp_path):
    """Integration-style test: set session, upload a payment proof, expect a PDF and a DB log."""
    student_hall = 'TESTHT123'

    # Add a temporary student row to the in-memory students DataFrame
    orig_len = len(students)
    new_row = {'HALLTICKET': student_hall, 'NAME': 'Test Student', 'STATUS': 'STUDYING'}
    # Append the new row
    students.loc[len(students)] = new_row

    # Set session values as the UI would
    with client.session_transaction() as sess:
        sess['cert_types'] = ['Bonafide']
        sess['hallticketno'] = student_hall
        sess['purpose'] = ''

    # Prepare file upload and transaction id
    data = {
        'transaction_id': 'TXN12345',
        'payment_proof': (io.BytesIO(b'testimagecontent'), 'proof.png')
    }

    # Post to verify_payment
    rv = client.post('/verify_payment', data=data, content_type='multipart/form-data')

    # Should return a PDF attachment when a single certificate is generated
    assert rv.status_code == 200
    assert 'application/pdf' in rv.headers.get('Content-Type', '')

    # Verify DB log created
    with app.app_context():
        rec = CertificateDownload.query.filter_by(student_hallticket=student_hall, transaction_id='TXN12345').first()
        assert rec is not None

    # Cleanup: remove uploaded file and DB entry, restore students DataFrame
    uploaded = os.path.join(app.config['UPLOAD_FOLDER'], f"{student_hall}_TXN12345.png")
    if os.path.exists(uploaded):
        os.remove(uploaded)

    with app.app_context():
        CertificateDownload.query.filter_by(student_hallticket=student_hall, transaction_id='TXN12345').delete()
        db.session.commit()

    # Remove the temporary student row
    students.drop(students[students['HALLTICKET'] == student_hall].index, inplace=True)
    assert len(students) == orig_len
