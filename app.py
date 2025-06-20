import os
from flask import Flask, request, jsonify, redirect, url_for, session, render_template
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Flask App Setup
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
app.config['SESSION_TYPE'] = 'filesystem'

# OAuth2 Config
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# # Create reusable Flow object
# flow = Flow.from_client_config({
#     "web": {
#         "client_id": GOOGLE_CLIENT_ID,
#         "client_secret": GOOGLE_CLIENT_SECRET,
#         "redirect_uris": [REDIRECT_URI],
#         "auth_uri": "https://accounts.google.com/o/oauth2/auth",
#         "token_uri": "https://oauth2.googleapis.com/token",
#         "scopes": SCOPES
#     }
# }, scopes=SCOPES)

def authenticate_drive():
    creds = None
    # Check if user has credentials stored in session
    if 'credentials' in session:
        creds = Credentials(**session['credentials'])

    # If no valid credentials are found, redirect to login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            return redirect(url_for('login'))  # Redirect to login if unauthenticated

    # Debugging: Check if credentials are valid and service is created
    try:
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        print(f"Error creating Google Drive service: {e}")
        return None

@app.route('/')
def index():
    if 'credentials' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login')
def login():
    flow = Flow.from_client_config({
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uris": [REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": SCOPES
        }
    }, scopes=SCOPES)
    
    flow.redirect_uri = url_for('callback', _external=True)
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    session['state'] = state
    return redirect(authorization_url)

@app.route('/callback')
def callback():
    flow.fetch_token(authorization_response=request.url)

    # Save the credentials in the session
    credentials = flow.credentials
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

    return redirect(url_for('index'))

@app.route('/get-folder', methods=['POST'])
def get_folder():
    service = authenticate_drive()

    # If the user is redirected to login or there's an error
    if isinstance(service, str):
        return service
    elif service is None:
        return jsonify({'error': 'Failed to authenticate and create Google Drive service'}), 500

    folder_id = request.json.get('folder_id')

    try:
        folder_html, file_html = list_folder_contents(service, folder_id)
        return jsonify({'folder_html': folder_html, 'file_html': file_html})
    except Exception as e:
        print(f"Error fetching folder contents: {e}")
        return jsonify({'error': 'Failed to fetch folder contents'}), 500

def list_folder_contents(service, folder_id, path='/', folder_html='', file_html='', level=0):
    folder = service.files().get(fileId=folder_id, fields='name').execute()
    folder_name = folder.get('name')
    current_path = os.path.join(path, folder_name)

    # Folder indentation
    folder_indent = '&nbsp;' * (level * 4)

    # Right panel folder tree structure
    folder_html += f'<div class="folder" id="right_{folder_id}" onclick="syncToLeftPanel(\'{folder_id}\')">{folder_indent}<b>{folder_name}</b></div>\n'
    
    # Left panel files and folder structure
    file_html += f'<div class="folder-title" id="left_{folder_id}" onclick="syncFolders(\'{folder_id}\')">{folder_indent}<b>{folder_name}</b></div>\n'

    query = f"'{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
    items = results.get('files', [])

    sub_folders_html = ''
    sub_files_html = ''

    for item in items:
        if item['mimeType'] == 'application/vnd.google-apps.folder':
            sub_folder_html, sub_file_html = list_folder_contents(service, item['id'], current_path, '', '', level + 1)
            sub_folders_html += sub_folder_html
            sub_files_html += sub_file_html
        else:
            file_extension = os.path.splitext(item['name'])[1]
            file_class = 'file'
            if file_extension in ['.xlsx', '.xlsm']:
                file_class += ' xlsx-file'

            file_indent = '-' * (level + 1)
            sub_files_html += f'<div class="{file_class}" style="margin-left: {level * 20}px;" onmouseover="highlightFolder(\'{folder_id}\')" onclick="showFullPath(\'{current_path}/{item["name"]}\')">{file_indent}{item["name"]}</div>\n'

    folder_html += sub_folders_html
    file_html += sub_files_html

    return folder_html, file_html

if __name__ == '__main__':
    import os
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))