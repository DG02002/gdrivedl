import os
import sys
import subprocess
import argparse
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import pickle
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
CYAN = '\033[96m'
RESET = '\033[0m'

default_download_path = "" #Enter path here 

parser = argparse.ArgumentParser(description='Google Drive Downloader with aria2 integration.')
parser.add_argument('--auth', metavar='OAuth_client', type=str, help='Set up OAuth 2.0 credentials to Access Google Drive APIs')
parser.add_argument('link', nargs='?', help='Google Drive Link')
args = parser.parse_args()

client_secret_file = args.auth
link = args.link

# Set up OAuth 2.0 credentials for Google Drive API
creds = None
creds_file = 'token.pickle'
if os.path.exists(creds_file):
    with open(creds_file, 'rb') as token:
        creds = pickle.load(token)
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            client_secret_file, ['https://www.googleapis.com/auth/drive'])
        creds = flow.run_local_server(port=0)
    with open(creds_file, 'wb') as token:
        pickle.dump(creds, token)
    print('The authentication is done.')
service = build('drive', 'v3', credentials=creds)

def download_file(file_id, file_name, file_size, dest_folder):
    cmd = [
        'aria2c',
        '--header=Authorization: Bearer {}'.format(creds.token),
        '--no-conf=true',
        '--continue=true',
        '--max-connection-per-server=16',
        '--split=10',
        '--console-log-level=error',
        '--file-allocation=none',
        '--summary-interval=0',
        '--max-tries=0',
        '--retry-wait=5',
        '-d', dest_folder,
        '-o', os.path.basename(file_name),
        'https://www.googleapis.com/drive/v3/files/{}?alt=media'.format(file_id)
    ]
    subprocess.run(cmd)

def get_total_files(folder_id):
    total_files = 0
    query = "'{}' in parents".format(folder_id)
    results = service.files().list(q=query, includeItemsFromAllDrives=True, supportsAllDrives=True, fields="nextPageToken, files(id, name, mimeType)").execute()
    items = results.get('files', [])
    for item in items:
        if item['mimeType'] == 'application/vnd.google-apps.folder':
            total_files += get_total_files(item['id'])
        else:
            total_files += 1
    return total_files

def download_folder(folder_id, folder_path, total_files=0, current_file=0):
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    query = "'{}' in parents".format(folder_id)
    results = service.files().list(q=query, includeItemsFromAllDrives=True, supportsAllDrives=True, fields="nextPageToken, files(id, name, mimeType, size)").execute()
    items = results.get('files', [])
    items = sorted(items, key=lambda x: x['name'])
    
    for item in items:
        file_id = item['id']
        file_name = os.path.join(folder_path, item['name'])
        file_size = int(item.get('size', 0))
        if item['mimeType'] == 'application/vnd.google-apps.folder':
            print('\nDownloading Subfolder {}{}{}'.format(CYAN, item['name'], RESET))
            total_files, current_file = download_folder(file_id, file_name, total_files, current_file)
        else:
            current_file += 1
            print('\n({}/{}) Found [{}{}{}]'.format(current_file, total_files, CYAN, os.path.basename(file_name), RESET))
            download_file(file_id, file_name, file_size, folder_path)
    return total_files, current_file

if __name__ == '__main__':
    if link:
        try:
            if '/file/d/' in link:
                file_id = link.split('/file/d/')[-1].split('/')[0]
            else:
                file_id = link.split('/')[-1].split('?')[0].split('&')[0]
            try:
                file = service.files().get(fileId=file_id, supportsAllDrives=True).execute()
            except HttpError as error:
                print('An error occurred: {}'.format(error))
                sys.exit(1)
            if file['mimeType'] == 'application/vnd.google-apps.folder':
                folder_path = os.path.join(default_download_path, file['name'])
                print('Downloading Folder {}{}{}'.format(CYAN, file['name'], RESET))
                total_files = get_total_files(file['id'])
                download_folder(file['id'], folder_path, total_files=total_files)
            else:
                file_name = os.path.join(default_download_path, file['name'])
                print('\nFound [{}{}{}]'.format(CYAN, os.path.basename(file_name), RESET))
                download_file(file['id'], file_name, int(file.get('size', 0)), default_download_path)
        except KeyboardInterrupt:
            print('\nCancelled')
