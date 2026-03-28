"""YouTube upload module for video publishing."""

import os
import json
from pathlib import Path
from typing import Optional, List

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeUploader:
    """Uploads videos to YouTube channel."""
    
    def __init__(self, client_secrets: str = "client_secrets.json",
                 credentials_path: str = "youtube_credentials.json"):
        self.client_secrets = client_secrets
        self.credentials_path = credentials_path
        self.service = None
    
    def _load_credentials(self) -> Optional[Credentials]:
        """Load credentials from JSON file."""
        if not os.path.exists(self.credentials_path):
            return None
        
        try:
            with open(self.credentials_path, 'r') as f:
                creds_data = json.load(f)
            
            return Credentials(
                token=creds_data.get('token'),
                refresh_token=creds_data.get('refresh_token'),
                token_uri=creds_data.get('token_uri'),
                client_id=creds_data.get('client_id'),
                client_secret=creds_data.get('client_secret'),
                scopes=creds_data.get('scopes')
            )
        except Exception as e:
            print(f"Error loading credentials: {e}")
            return None
    
    def _save_credentials(self, creds: Credentials):
        """Save credentials to JSON file with validation."""
        # Validate required fields
        if not creds.refresh_token:
            print("Warning: No refresh token available. Credentials may expire.")
        
        creds_data = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes
        }
        
        # Validate no critical fields are None
        required_fields = ['client_id', 'client_secret', 'token_uri']
        for field in required_fields:
            if not creds_data.get(field):
                raise ValueError(f"Cannot save credentials: {field} is missing")
        
        with open(self.credentials_path, 'w') as f:
            json.dump(creds_data, f, indent=2)
        
        # Set secure file permissions (owner read/write only)
        try:
            import stat
            os.chmod(self.credentials_path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception as e:
            print(f"Warning: Could not set secure permissions on credentials file: {e}")
    
    def authenticate(self) -> bool:
        """Authenticate with YouTube API."""
        creds = self._load_credentials()
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.client_secrets):
                    print(f"ERROR: {self.client_secrets} not found!")
                    print("Download it from Google Cloud Console")
                    return False
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secrets, SCOPES)
                creds = flow.run_local_server(port=8080)
            
            self._save_credentials(creds)
        
        self.service = build("youtube", "v3", credentials=creds)
        return True
    
    def upload_video(self, video_path: str, title: str, description: str,
                    tags: List[str], category: str = "22",  # 22 = People & Blogs
                    privacy: str = "private") -> Optional[str]:
        """Upload a video to YouTube."""
        if not self.service:
            if not self.authenticate():
                return None
        
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": category
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False
            }
        }
        
        try:
            media = MediaFileUpload(video_path, resumable=True)
            request = self.service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )
            
            print(f"Uploading {video_path}...")
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"Upload {int(status.progress() * 100)}%")
            
            video_id = response["id"]
            print(f"Upload complete! Video ID: {video_id}")
            print(f"URL: https://youtube.com/watch?v={video_id}")
            
            return video_id
            
        except HttpError as e:
            print(f"Upload failed: {e}")
            return None
    
    def set_thumbnail(self, video_id: str, thumbnail_path: str) -> bool:
        """Set custom thumbnail for a video."""
        if not self.service:
            return False
        
        try:
            media = MediaFileUpload(thumbnail_path)
            self.service.thumbnails().set(
                videoId=video_id,
                media_body=media
            ).execute()
            print("Thumbnail updated!")
            return True
        except HttpError as e:
            print(f"Thumbnail update failed: {e}")
            return False
    
    def update_video_metadata(self, video_id: str, 
                             title: Optional[str] = None,
                             description: Optional[str] = None,
                             tags: Optional[List[str]] = None) -> bool:
        """Update video metadata after upload."""
        if not self.service:
            return False
        
        body = {"id": video_id, "snippet": {}}
        
        if title:
            body["snippet"]["title"] = title
        if description:
            body["snippet"]["description"] = description
        if tags:
            body["snippet"]["tags"] = tags
        
        try:
            self.service.videos().update(
                part="snippet",
                body=body
            ).execute()
            print("Metadata updated!")
            return True
        except HttpError as e:
            print(f"Metadata update failed: {e}")
            return False


if __name__ == "__main__":
    uploader = YouTubeUploader()
    
    if uploader.authenticate():
        print("Authentication successful!")
        # Example upload (requires actual video file)
        # video_id = uploader.upload_video(
        #     "output/final_video.mp4",
        #     "Test Video",
        #     "This is a test upload",
        #     ["test", "automation"],
        #     privacy="private"
        # )
