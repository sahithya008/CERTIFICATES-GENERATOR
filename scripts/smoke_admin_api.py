import os
import sys
import uuid
import base64
import pandas as pd

# Ensure project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app, EXCEL_FILE


def add_student_session_auth(client, hall):
    with client.session_transaction() as sess:
        sess['admin'] = True
    rv = client.post('/admin/api/students', json={'HALLTICKET': hall, 'NAME': 'Smoke Test', 'STATUS': 'STUDYING'})
    return rv


def add_student_basic_auth(client, hall, user, pwd):
    token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
    headers = {'Authorization': f'Basic {token}'}
    rv = client.post('/admin/api/students', json={'HALLTICKET': hall, 'NAME': 'Smoke Test Basic', 'STATUS': 'STUDYING'}, headers=headers)
    return rv


def exists_in_excel(hall):
    df = pd.read_excel(EXCEL_FILE, engine='openpyxl')
    return hall in df['HALLTICKET'].astype(str).values


def remove_from_excel(hall):
    df = pd.read_excel(EXCEL_FILE, engine='openpyxl')
    df = df[df['HALLTICKET'].astype(str) != hall]
    df.to_excel(EXCEL_FILE, index=False, engine='openpyxl')


if __name__ == '__main__':
    client = app.test_client()

    print('Running session-auth smoke test...')
    hall = 'SMOKETEST_' + uuid.uuid4().hex[:8]
    rv = add_student_session_auth(client, hall)
    print('Status:', rv.status_code, rv.get_data(as_text=True))
    if rv.status_code == 201 and exists_in_excel(hall):
        print('Session-auth: success, entry present in Excel')
    else:
        print('Session-auth: FAILED')
    # cleanup
    try:
        remove_from_excel(hall)
        print('Session-auth: cleaned up')
    except Exception as e:
        print('Session-auth: cleanup failed', e)

    print('\nRunning basic-auth smoke test...')
    # Temporarily set admin credentials
    orig_user = getattr(app, 'ADMIN_USERNAME', None)
    orig_pwd = getattr(app, 'ADMIN_PASSWORD', None)
    app.ADMIN_USERNAME = 'smokeuser'
    app.ADMIN_PASSWORD = 'smokepass'

    hall2 = 'SMOKETESTB_' + uuid.uuid4().hex[:8]
    rv2 = add_student_basic_auth(client, hall2, 'smokeuser', 'smokepass')
    print('Status:', rv2.status_code, rv2.get_data(as_text=True))
    if rv2.status_code == 201 and exists_in_excel(hall2):
        print('Basic-auth: success, entry present in Excel')
    else:
        print('Basic-auth: FAILED')

    # cleanup
    try:
        remove_from_excel(hall2)
        print('Basic-auth: cleaned up')
    except Exception as e:
        print('Basic-auth: cleanup failed', e)

    # restore
    app.ADMIN_USERNAME = orig_user
    app.ADMIN_PASSWORD = orig_pwd

    print('\nSmoke checks finished.')
