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

print("🔍 [DEBUG] CURRENT REDIRECT_URI =", REDIRECT_URI)

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

    flow.fetch_token(authorization_response=request.url)

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

    if isinstance(service, str):
        return service
    elif service is None:
        return jsonify({'error': 'Failed to authenticate and create Google Drive service'}), 500

    folder_id = request.json.get('folder_id')

    try:
        folder_html_left, folder_html_right, file_html = list_folder_contents(service, folder_id)

        # Fetch the folder's name for the response
        folder = service.files().get(fileId=folder_id, fields='name').execute()
        folder_name = folder.get('name')

        # Create the link to the folder
        folder_link = f'<a href="https://drive.google.com/drive/folders/{folder_id}" target="_blank">Open in Google Drive</a>'

        return jsonify({
            'folder_html_left': folder_html_left,
            'folder_html_right': folder_html_right,
            'file_html': file_html,
            'folder_name': folder_name,  # Return the folder name in the response
            'folder_link': folder_link    # Return the folder link
        })
    except Exception as e:
        print(f"Error fetching folder contents: {e}")
        return jsonify({'error': 'Failed to fetch folder contents'}), 500

def list_folder_contents(service, folder_id, path='/', folder_html_left='', folder_html_right='', file_html='', level=0):
    # Fetch the folder details
    folder = service.files().get(fileId=folder_id, fields='name').execute()
    folder_name = folder.get('name')
    current_path = os.path.join(path, folder_name)

    # Folder indentation
    folder_indent = '&nbsp;' * (level * 4)

    # Right panel folder tree structure
    folder_html_right += f'<div class="folder" id="right_{folder_id}" onclick="syncToLeftPanel(\'{folder_id}\')">{folder_indent}<b>{folder_name}</b></div>\n'

    # Left panel folder structure with toggle button and indentation
    folder_html_left += f'<div class="folder-title" id="left_{folder_id}" onclick="toggleFolder(\'{folder_id}\', this)">{folder_indent}<span class="folder-icon" style="transform: rotate(45deg);">+</span> <b>{folder_name}</b></div>\n'

    # Initially show the contents for folders in the left panel
    folder_html_left += f'<div class="folder-contents" id="contents_{folder_id}" style="display: block; margin-left: {level * 20}px;">\n'

    # Query to list contents of the folder
    query = f"'{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
    items = results.get('files', [])

    # Temporary lists for files and folders
    files_list = []
    folders_list = []

    # Separate files and folders
    for item in items:
        if item['mimeType'] == 'application/vnd.google-apps.folder':
            folders_list.append(item)  # Store folders for later processing
        else:
            files_list.append(item)  # Store non-folders for immediate processing

    # Process non-folder items first
    for item in files_list:
        file_indent = '-' * (level + 1)
        folder_html_left += f'<div class="file" style="margin-left: {level * 20}px;" onmouseover="highlightFolder(\'{folder_id}\')" onclick="showFullPath(\'{current_path}/{item["name"]}\')">{file_indent} {item["name"]}</div>\n'

    # Now process folder items
    for item in folders_list:
        sub_folder_html_left, sub_folder_html_right, sub_file_html = list_folder_contents(service, item['id'], current_path, '', '', '', level + 1)
        folder_html_left += sub_folder_html_left
        folder_html_right += sub_folder_html_right
        folder_html_left += sub_file_html  # Add files from subfolders into the left panel

    folder_html_left += '</div>\n'  # Close the folder contents div

    return folder_html_left, folder_html_right, file_html

if __name__ == '__main__':
    import os
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))