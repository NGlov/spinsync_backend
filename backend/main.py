from flask import Flask, redirect, request, session, jsonify
from flask_cors import CORS
from flask_session import Session
import requests
import urllib.parse
from datetime import datetime

app = Flask(__name__)
SESSION_COOKIE_NAME="spotify_session"
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = False
app.secret_key = '23eindinw30448qwqiwsis2'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

CORS(app, supports_credentials=True, origins=["http://127.0.0.1:3000"])

CLIENT_ID = "f7e0ea7286404851a7fa5a973b7c4805"
CLIENT_SECRET = "5bcc016a5ffb4a4fa1377c7b8c391c74"
REDIRECT_URI = "http://127.0.0.1:5000/callback"
AUTH_URL = 'https://accounts.spotify.com/authorize'
TOKEN_URL = 'https://accounts.spotify.com/api/token'

def get_access_token():
    if 'access_token' not in session:
        return None

    if datetime.now().timestamp() > session.get('expires_at', 0):
        if 'refresh_token' not in session:
            session.pop('access_token', None)
            session.pop('expires_at', None)
            return None
        
        req_body = {
            'grant_type': 'refresh_token',
            'refresh_token': session['refresh_token'],
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET
        }
        response = requests.post(TOKEN_URL, data=req_body)
        if response.status_code != 200:
            session.pop('access_token', None)
            session.pop('expires_at', None)
            session.pop('refresh_token', None)
            return None
        
        new_token_info = response.json()
        session['access_token'] = new_token_info['access_token']
        session['expires_at'] = datetime.now().timestamp() + new_token_info.get('expires_in', 3600)
        session.modified = True

    return session['access_token']

@app.route("/test-playlist", methods=['POST'])
def test_playlist():
    return jsonify({"message": "Playlist route works!"})

@app.route('/')
def home():
        return redirect("/login")

@app.route('/login')
def login():
    scope = 'playlist-modify-public playlist-modify-private playlist-read-private user-read-playback-state user-modify-playback-state user-read-currently-playing user-read-recently-played user-top-read'
    params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'scope': scope,
        'redirect_uri': REDIRECT_URI,
        'show_dialog': True,     
        'prompt': 'consent'        
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    return redirect(auth_url)


@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return jsonify({"error": "Missing authorization code"}), 400

    req_body = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    response = requests.post(TOKEN_URL, data=req_body)
    token_data = response.json()
    
    if 'access_token' not in token_data:
        return jsonify({"error": "Failed to get access token", "details": token_data}), 400
    print("Token response:", token_data)
    session['access_token'] = token_data['access_token']
    session['expires_at'] = datetime.now().timestamp() + token_data['expires_in']
    print("Session after callback:", dict(session))
    if 'refresh_token' in token_data:
        session['refresh_token'] = token_data['refresh_token']
    return redirect("http://127.0.0.1:3000/dashboard")

@app.route('/refresh-token')
def refresh_token():
    if 'refresh_token' not in session:
        return jsonify({"error": "No refresh token in session"}), 401

    req_body = {
        'grant_type': 'refresh_token',
        'refresh_token': session['refresh_token'],
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    response = requests.post(TOKEN_URL, data=req_body)
    new_token_info = response.json()

    if 'access_token' not in new_token_info:
        return jsonify({"error": "Failed to refresh token", "details": new_token_info}), 400

    session['access_token'] = new_token_info['access_token']
    session['expires_at'] = datetime.now().timestamp() + new_token_info.get('expires_in', 3600)

    return jsonify({"message": "Token refreshed successfully"})

@app.route('/me')
def me():
    access_token = get_access_token()
    if not access_token:
        return jsonify({"error": "Unauthorized"}), 401

    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get("https://api.spotify.com/v1/me", headers=headers)
    return jsonify(response.json())

@app.route('/history/top-tracks')
def top_tracks():
    access_token = session.get("access_token")
    if not access_token:
        return jsonify({"error": "Unauthorized"}), 401
    
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"limit": 5, "time_range": "short_term"} 
    r = requests.get("https://api.spotify.com/v1/me/top/tracks", headers=headers, params=params)
    return jsonify(r.json())

def refresh_access_token():
    if 'refresh_token' not in session:
        return None
    req_body = {
        'grant_type': 'refresh_token',
        'refresh_token': session['refresh_token'],
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    response = requests.post(TOKEN_URL, data=req_body)
    new_token_info = response.json()
    if 'access_token' not in new_token_info:
        return None
    session['access_token'] = new_token_info['access_token']
    session['expires_at'] = datetime.now().timestamp() + new_token_info.get('expires_in', 3600)
    return True

@app.route('/playlist', methods=['POST', 'OPTIONS'])
def create_playlist():
    if request.method == 'OPTIONS':
        return app.make_default_options_response()

    access_token = session.get("access_token")
    if not access_token:
        return jsonify({"error": "Unauthorized"}), 401

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    me_resp = requests.get("https://api.spotify.com/v1/me", headers=headers)
    if me_resp.status_code != 200:
        return jsonify({"error": "Failed to get user profile"}), me_resp.status_code
    me = me_resp.json()
    market = me.get("country", "US")
    user_id = me.get("id")

    top_artists_resp = requests.get("https://api.spotify.com/v1/me/top/artists?limit=10", headers=headers)
    top_artists = top_artists_resp.json().get("items", []) if top_artists_resp.status_code == 200 else []
    top_artist_ids = [a["id"] for a in top_artists]

    related_artist_ids = []
    for aid in top_artist_ids:
        ra_resp = requests.get(f"https://api.spotify.com/v1/artists/{aid}/related-artists", headers=headers)
        if ra_resp.status_code == 200:
            ra = ra_resp.json().get("artists", [])
            related_artist_ids.extend([x["id"] for x in ra[:2]])
    related_artist_ids = list(dict.fromkeys(related_artist_ids))

    top_tracks_resp = requests.get("https://api.spotify.com/v1/me/top/tracks?limit=20", headers=headers)
    top_tracks = top_tracks_resp.json().get("items", []) if top_tracks_resp.status_code == 200 else []

    recent_resp = requests.get("https://api.spotify.com/v1/me/player/recently-played?limit=20", headers=headers)
    recent_tracks = [it["track"] for it in recent_resp.json().get("items", []) if "track" in it] if recent_resp.status_code == 200 else []

    seen_track_ids = set([t["id"] for t in top_tracks] + [t["id"] for t in recent_tracks])

    candidate_tracks = []
    if related_artist_ids:
        for rid in related_artist_ids:
            tt_resp = requests.get(
                f"https://api.spotify.com/v1/artists/{rid}/top-tracks",
                headers=headers,
                params={"market": market}
            )
            if tt_resp.status_code == 200:
                for tr in tt_resp.json().get("tracks", []):
                    if tr["id"] not in seen_track_ids:
                        candidate_tracks.append(tr)

    if not candidate_tracks and top_tracks:
        candidate_tracks = top_tracks
    elif not candidate_tracks and recent_tracks:
        candidate_tracks = recent_tracks

    if not candidate_tracks:
        return jsonify({"error": "No tracks available to generate a playlist"}), 400

    unique = []
    seen = set()
    for tr in candidate_tracks:
        if tr["id"] not in seen:
            unique.append(tr)
            seen.add(tr["id"])
        if len(unique) >= 30:
            break

    uris = [t["uri"] for t in unique]

    playlist_info = {
        "name": "SpinSync Playlist",
        "description": "A playlist made for you!",
        "public": False
    }
    pl_resp = requests.post(
        f"https://api.spotify.com/v1/users/{user_id}/playlists",
        headers=headers,
        json=playlist_info
    )
    if pl_resp.status_code != 201:
        return jsonify({"error": "Failed to create playlist"}), pl_resp.status_code

    playlist = pl_resp.json()
    playlist_id = playlist.get("id")

    add_resp = requests.post(
        f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
        headers=headers,
        json={"uris": uris}
    )
    if add_resp.status_code != 201:
        return jsonify({"error": "Failed to add tracks"}), add_resp.status_code

    playlist_url = playlist.get("external_urls", {}).get("spotify")
    return jsonify({"message": "Playlist created!", "playlist_url": playlist_url})


@app.route("/history/recent-tracks")
def recent_tracks():
    access_token = session.get("access_token")
    if not access_token:
        return jsonify({"error": "Unauthorized"}), 401

    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(
        "https://api.spotify.com/v1/me/player/recently-played?limit=5",
        headers=headers
    )
    print("Spotify recent tracks response:", response.status_code, response.text)

    if response.status_code != 200:
        return jsonify({"error": "Unable to fetch data"}), response.status_code

    data = response.json()
    tracks = []
    for item in data.get("items", []):
        track = item["track"]
        tracks.append({
            "name": track["name"],
            "artists": [artist["name"] for artist in track["artists"]],
            "album": track["album"]["name"],
            "album_art": track["album"]["images"][0]["url"],
            "played_at": item["played_at"] 
        })

    return jsonify(tracks)


if __name__ == '__main__':
    app.run(host="127.0.0.1", port=5000, debug=True)
