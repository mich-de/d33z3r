import os
import json
import threading
import requests as req
from flask import Flask, render_template_string, request, jsonify, send_file, Response
from deemix.settings import DEFAULTS
from deemix import generateDownloadObject
from deemix.downloader import Downloader
from deemix.utils.crypto import generateBlowfishKey, decryptChunk
from deezer import Deezer

app = Flask(__name__)

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Range, Content-Type'
    response.headers['Access-Control-Expose-Headers'] = 'Content-Length, Content-Range, Accept-Ranges'
    return response

def load_arl():
    arl_path = os.path.join(os.path.dirname(__file__), 'arl.txt')
    with open(arl_path) as f:
        for line in f:
            if line.startswith('arl:'):
                return line.split('arl:', 1)[1].strip()
    return None

ARL = load_arl()
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), 'music')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
downloads = {}

def get_dz():
    dz = Deezer()
    dz.login_via_arl(ARL)
    return dz

def norm_track(t):
    return {
        'id': t.get('id'),
        'title': t.get('title', ''),
        'artist': t.get('artist', {}).get('name', '') if isinstance(t.get('artist'), dict) else str(t.get('artist', '')),
        'artist_id': t.get('artist', {}).get('id') if isinstance(t.get('artist'), dict) else None,
        'album': t.get('album', {}).get('title', '') if isinstance(t.get('album'), dict) else str(t.get('album', '')),
        'album_id': t.get('album', {}).get('id') if isinstance(t.get('album'), dict) else None,
        'cover': (t.get('album', {}).get('cover_medium') or t.get('album', {}).get('cover_big') or t.get('album', {}).get('cover') or '') if isinstance(t.get('album'), dict) else '',
        'duration': t.get('duration', 0),
        'preview': t.get('preview', ''),
        'position': t.get('position', 0),
    }

def norm_album(a):
    return {
        'id': a.get('id'),
        'title': a.get('title', ''),
        'artist': a.get('artist', {}).get('name', '') if isinstance(a.get('artist'), dict) else str(a.get('artist', '')),
        'artist_id': a.get('artist', {}).get('id') if isinstance(a.get('artist'), dict) else None,
        'cover': a.get('cover_medium') or a.get('cover_big') or a.get('cover', ''),
        'nb_tracks': a.get('nb_tracks', 0),
    }

def norm_playlist(p):
    return {
        'id': p.get('id'),
        'name': p.get('title', ''),
        'image': p.get('picture_medium') or p.get('picture_big') or p.get('picture', ''),
        'owner': p.get('user', {}).get('name', '') if isinstance(p.get('user'), dict) else '',
        'nb_tracks': p.get('nb_tracks', 0),
    }

def norm_artist(a):
    return {
        'id': a.get('id'),
        'name': a.get('name', ''),
        'image': a.get('picture_medium') or a.get('picture_big') or a.get('picture', ''),
        'nb_album': a.get('nb_album', 0),
    }

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/api/status')
def status():
    return jsonify({'arl': bool(ARL)})

@app.route('/api/trending')
def trending():
    try:
        charts = req.get('https://api.deezer.com/chart', timeout=10).json()
        releases = req.get('https://api.deezer.com/editorial/0/releases', timeout=10).json()
        return jsonify({
            'chart_tracks': [norm_track(t) for t in charts.get('tracks', {}).get('data', [])[:20]],
            'chart_albums': [norm_album(a) for a in charts.get('albums', {}).get('data', [])[:18]],
            'chart_playlists': [norm_playlist(p) for p in charts.get('playlists', {}).get('data', [])[:12]],
            'new_releases': [norm_album(a) for a in releases.get('data', [])[:18]]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/genres')
def genres():
    try:
        data = req.get('https://api.deezer.com/genre', timeout=10).json()
        genres_list = data.get('data', [])
        return jsonify({'genres': genres_list})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/genre/<int:gid>/radio')
def genre_radio(gid):
    try:
        data = req.get(f'https://api.deezer.com/genre/{gid}/radios', timeout=10).json()
        return jsonify({'radios': data.get('data', [])})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/playlist/<pid>')
def playlist_info(pid):
    try:
        pl = req.get(f'https://api.deezer.com/playlist/{pid}', timeout=10).json()
        tracks = req.get(f'https://api.deezer.com/playlist/{pid}/tracks?limit=100', timeout=10).json()
        return jsonify({'playlist': norm_playlist(pl), 'tracks': [norm_track(t) for t in tracks.get('data', [])]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/album/<aid>')
def album_info(aid):
    try:
        al = req.get(f'https://api.deezer.com/album/{aid}', timeout=10).json()
        tracks = req.get(f'https://api.deezer.com/album/{aid}/tracks', timeout=10).json()
        # Inject album cover into each track (Deezer API doesn't include it)
        album_cover = al.get('cover_medium') or al.get('cover_big') or al.get('cover', '')
        track_list = []
        for t in tracks.get('data', []):
            nt = norm_track(t)
            if not nt['cover']:
                nt['cover'] = album_cover
            track_list.append(nt)
        return jsonify({'album': norm_album(al), 'tracks': track_list})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/search')
def search():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'error': 'empty query'}), 400
    try:
        tracks = req.get(f'https://api.deezer.com/search?q={q}&limit=30', timeout=10).json()
        playlists = req.get(f'https://api.deezer.com/search/playlist?q={q}&limit=10', timeout=10).json()
        albums = req.get(f'https://api.deezer.com/search/album?q={q}&limit=10', timeout=10).json()
        artists = req.get(f'https://api.deezer.com/search/artist?q={q}&limit=8', timeout=10).json()
        return jsonify({
            'tracks': [norm_track(t) for t in tracks.get('data', [])],
            'playlists': [norm_playlist(p) for p in playlists.get('data', [])],
            'albums': [norm_album(a) for a in albums.get('data', [])],
            'artists': [norm_artist(a) for a in artists.get('data', [])]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/artist/<aid>')
def artist_info(aid):
    try:
        artist = req.get(f'https://api.deezer.com/artist/{aid}', timeout=10).json()
        top = req.get(f'https://api.deezer.com/artist/{aid}/top?limit=20', timeout=10).json()
        albums = req.get(f'https://api.deezer.com/artist/{aid}/albums?limit=20', timeout=10).json()
        return jsonify({
            'artist': norm_artist(artist),
            'top': [norm_track(t) for t in top.get('data', [])],
            'albums': [norm_album(a) for a in albums.get('data', [])]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/radios')
def radios():
    try:
        data = req.get('https://api.deezer.com/radio', timeout=10).json()
        return jsonify({'radios': data.get('data', [])[:12]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/new_releases')
def new_releases():
    try:
        data = req.get('https://api.deezer.com/editorial/0/releases', timeout=10).json()
        return jsonify({'albums': [norm_album(a) for a in data.get('data', [])[:18]]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/track_info/<int:track_id>')
def track_info(track_id):
    try:
        data = req.get(f'https://api.deezer.com/track/{track_id}', timeout=10).json()
        return jsonify(norm_track(data))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stream_track/<int:track_id>')
def stream_track(track_id):
    try:
        dz = get_dz()
        track = dz.gw.get_track(track_id)
        track_token = track.get('TRACK_TOKEN', '')
        if not track_token:
            return jsonify({'error': 'no token for track ' + str(track_id)}), 404
        url = dz.get_track_url(track_token, 'MP3_128')
        if not url:
            return jsonify({'error': 'no url for track ' + str(track_id)}), 404
        headers = {'User-Agent': 'Deezer/6.23.0.0'}
        range_header = request.headers.get('Range')
        if range_header:
            headers['Range'] = range_header
        r = req.get(url, timeout=30, stream=True, headers=headers)
        resp_headers = {
            'Content-Type': 'audio/mpeg',
            'Accept-Ranges': 'bytes',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Range',
            'Access-Control-Expose-Headers': 'Content-Length, Content-Range, Accept-Ranges',
        }
        # Do NOT forward Content-Length when decrypting — decrypted size differs from encrypted
        if 'Content-Range' in r.headers:
            resp_headers['Content-Range'] = r.headers['Content-Range']
        bf_key = generateBlowfishKey(str(track_id))
        CHUNK_SIZE = 2048 * 3
        def generate():
            for chunk in r.iter_content(CHUNK_SIZE):
                if chunk:
                    if len(chunk) >= 2048:
                        decrypted = decryptChunk(bf_key, chunk[:2048]) + chunk[2048:]
                        yield decrypted
                    else:
                        yield chunk
        status = 206 if r.status_code == 206 else 200
        return Response(generate(), status=status, headers=resp_headers)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stream_preview/<int:track_id>')
def stream_preview(track_id):
    try:
        resp = req.get(f'https://api.deezer.com/track/{track_id}', timeout=10)
        data = resp.json()
        preview = data.get('preview')
        if not preview:
            return '', 404
        r = req.get(preview, timeout=20, stream=True)
        return Response(r.iter_content(chunk_size=8192), content_type='audio/mpeg')
    except Exception as e:
        return '', 502

@app.route('/api/proxy_audio')
def proxy_audio():
    url = request.args.get('url', '')
    if not url:
        return '', 400
    try:
        r = req.get(url, timeout=15, stream=True)
        return Response(r.iter_content(chunk_size=8192), content_type=r.headers.get('Content-Type', 'audio/mpeg'))
    except:
        return '', 502

@app.route('/api/proxy_image')
def proxy_image():
    url = request.args.get('url', '')
    if not url:
        return '', 400
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.deezer.com/',
        }
        r = req.get(url, timeout=10, headers=headers)
        ct = r.headers.get('Content-Type', 'image/jpeg')
        return Response(r.content, content_type=ct, headers={'Cache-Control': 'public, max-age=86400'})
    except:
        return '', 502

@app.route('/api/download', methods=['POST'])
def download():
    data = request.json
    link = data.get('link', '').strip()
    album_title = data.get('album_title', '').strip()
    artist_name = data.get('artist_name', '').strip()
    if not link:
        return jsonify({'error': 'Nessun link'}), 400
    dl_id = str(len(downloads) + 1)
    downloads[dl_id] = {'status': 'starting', 'link': link, 'title': '', 'progress': 0}
    def run():
        try:
            dz = get_dz()
            if not dz.logged_in:
                downloads[dl_id].update(status='error', error='Login fallito')
                return
            settings = DEFAULTS.copy()
            if album_title and artist_name:
                safe_artist = "".join(c for c in artist_name if c.isalnum() or c in ' -_&').strip()
                safe_album = "".join(c for c in album_title if c.isalnum() or c in ' -_&').strip()
                folder = os.path.join(DOWNLOAD_DIR, f"{safe_artist} - {safe_album}")
                os.makedirs(folder, exist_ok=True)
                settings['downloadLocation'] = folder
            else:
                settings['downloadLocation'] = DOWNLOAD_DIR
            obj = generateDownloadObject(dz, link, settings)
            obj.bitrate = 1
            downloads[dl_id]['title'] = getattr(obj, 'title', link)
            downloads[dl_id]['status'] = 'downloading'
            dl = Downloader(dz, obj, settings)
            dl.start()
            downloads[dl_id].update(status='done', progress=100)
        except Exception as e:
            downloads[dl_id].update(status='error', error=str(e))
    threading.Thread(target=run, daemon=True).start()
    return jsonify({'id': dl_id})

@app.route('/api/download_batch', methods=['POST'])
def download_batch():
    data = request.json
    ids = data.get('track_ids', [])
    if not ids:
        return jsonify({'error': 'No tracks'}), 400
    bid = str(len(downloads) + 1)
    downloads[bid] = {'status': 'downloading', 'title': f'{len(ids)} tracce', 'progress': 0, 'total': len(ids), 'completed': 0}
    def run():
        dz = get_dz()
        if not dz.logged_in:
            downloads[bid].update(status='error', error='Login fallito')
            return
        settings = DEFAULTS.copy()
        settings['downloadLocation'] = DOWNLOAD_DIR
        for i, tid in enumerate(ids):
            try:
                obj = generateDownloadObject(dz, f'https://www.deezer.com/track/{tid}', settings)
                obj.bitrate = 1
                Downloader(dz, obj, settings).start()
                downloads[bid]['completed'] = i + 1
                downloads[bid]['progress'] = int((i + 1) / len(ids) * 100)
            except:
                pass
        downloads[bid].update(status='done', progress=100)
    threading.Thread(target=run, daemon=True).start()
    return jsonify({'id': bid})

@app.route('/api/downloads')
def get_downloads():
    return jsonify(downloads)

@app.route('/api/settings')
def get_settings():
    creds = {'email': '', 'password': '', 'arl': ARL, 'created': ''}
    arl_path = os.path.join(os.path.dirname(__file__), 'arl.txt')
    try:
        with open(arl_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith('email:'):
                    creds['email'] = line.split('email:', 1)[1].strip()
                elif line.startswith('password:'):
                    creds['password'] = line.split('password:', 1)[1].strip()
                elif line.startswith('arl:'):
                    creds['arl'] = line.split('arl:', 1)[1].strip()
                elif line.startswith('created:'):
                    creds['created'] = line.split('created:', 1)[1].strip()
    except:
        pass
    # Also try result.json for timestamp
    if not creds['created']:
        rj = os.path.join(os.path.dirname(__file__), 'result.json')
        try:
            with open(rj) as f:
                data = json.load(f)
                creds['created'] = data.get('timestamp', '')
        except:
            pass
    return jsonify(creds)

@app.route('/api/generate_arl', methods=['POST'])
def generate_arl():
    from datetime import datetime
    bid = str(len(downloads) + 1)
    downloads[bid] = {
        'status': 'generating', 'title': 'Generazione ARL...', 'progress': 0,
        'logs': [], 'start_time': datetime.now().strftime('%H:%M:%S'),
        'end_time': '', 'verified': False
    }
    def log(msg):
        ts = datetime.now().strftime('%H:%M:%S')
        downloads[bid]['logs'].append(f'[{ts}] {msg}')
    def run():
        global ARL
        start = datetime.now()
        downloads[bid]['start_time'] = start.strftime('%H:%M:%S')
        try:
            import subprocess
            log('Avvio registrazione account Deezer...')
            downloads[bid]['progress'] = 10
            log('Eseguo register-final.js...')
            downloads[bid]['progress'] = 20
            result = subprocess.run(
                ['node', 'register-final.js'],
                cwd=os.path.dirname(__file__) or '.',
                capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                log(f'Errore Node.js: {result.stderr[:200]}')
                downloads[bid].update(status='error', error=result.stderr[:500])
                return
            log('Script completato. Leggo result.json...')
            downloads[bid]['progress'] = 50
            rj = os.path.join(os.path.dirname(__file__), 'result.json')
            if not os.path.exists(rj):
                log('ERRORE: result.json non trovato')
                downloads[bid].update(status='error', error='result.json non trovato')
                return
            with open(rj) as f:
                data = json.load(f)
            new_email = data.get('email', '')
            new_pass = data.get('password', '')
            new_arl = data.get('arl', '')
            if not new_arl:
                log('ERRORE: Nessun ARL nel risultato')
                downloads[bid].update(status='error', error='Nessun ARL nel risultato')
                return
            log(f'Email: {new_email}')
            log(f'ARL trovato: {new_arl[:20]}...')
            downloads[bid]['progress'] = 60
            log('Verifico che l\'ARL sia funzionante...')
            try:
                test_dz = Deezer()
                test_dz.login_via_arl(new_arl)
                if test_dz.logged_in:
                    log('ARL verificato: login OK!')
                    downloads[bid]['verified'] = True
                else:
                    log('ARL verificato: login fallito (ma potrebbe funzionare)')
                    downloads[bid]['verified'] = False
            except Exception as ve:
                log(f'Avviso verifica: {ve}')
                downloads[bid]['verified'] = False
            downloads[bid]['progress'] = 80
            log('Salvo credenziali in arl.txt...')
            ARL = new_arl
            with open(os.path.join(os.path.dirname(__file__), 'arl.txt'), 'w') as f:
                f.write(f'email: {new_email}\npassword: {new_pass}\narl: {new_arl}\ncreated: {data.get("timestamp", "")}\n')
            end = datetime.now()
            elapsed = (end - start).total_seconds()
            log(f'Completato in {elapsed:.1f}s')
            downloads[bid].update(
                status='done', progress=100,
                arl=new_arl, email=new_email, password=new_pass,
                created=data.get('timestamp', ''),
                end_time=end.strftime('%H:%M:%S'),
                elapsed=f'{elapsed:.1f}s'
            )
        except subprocess.TimeoutExpired:
            log('ERRORE: Timeout (120s)')
            downloads[bid].update(status='error', error='Timeout (120s)')
        except Exception as e:
            log(f'ERRORE: {e}')
            downloads[bid].update(status='error', error=str(e))
    threading.Thread(target=run, daemon=True).start()
    return jsonify({'id': bid})

@app.route('/api/files/<filename>')
def serve_file(filename):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return '', 404

@app.route('/api/stream/<filename>')
def stream_file(filename):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(path):
        return send_file(path, mimetype='audio/mpeg')
    return '', 404

CHART_PLAYLISTS = {
    'worldwide': {'id': 3155776842, 'name': 'Worldwide', 'flag': '🌍'},
    'italy':     {'id': 1116187241, 'name': 'Italia',    'flag': '🇮🇹'},
    'france':    {'id': 1109890291, 'name': 'France',    'flag': '🇫🇷'},
    'usa':       {'id': 1313621735, 'name': 'USA',       'flag': '🇺🇸'},
    'uk':        {'id': 1111142221, 'name': 'UK',        'flag': '🇬🇧'},
    'germany':   {'id': 1111143121, 'name': 'Germany',   'flag': '🇩🇪'},
    'spain':     {'id': 1116190041, 'name': 'Spain',     'flag': '🇪🇸'},
    'brazil':    {'id': 1111141961, 'name': 'Brazil',    'flag': '🇧🇷'},
    'japan':     {'id': 1362508955, 'name': 'Japan',     'flag': '🇯🇵'},
}

@app.route('/api/charts')
def charts():
    try:
        data = req.get('https://api.deezer.com/chart', timeout=10).json()
        playlists = data.get('playlists', {}).get('data', [])[:18]
        tracks = data.get('tracks', {}).get('data', [])[:20]
        albums = data.get('albums', {}).get('data', [])[:18]
        podcasts = data.get('podcasts', {}).get('data', [])[:12]
        return jsonify({'playlists': playlists, 'top_tracks': tracks, 'albums': albums, 'podcasts': podcasts})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chart/<country>')
def country_chart(country):
    info = CHART_PLAYLISTS.get(country.lower())
    if not info:
        return jsonify({'error': f'Unknown country: {country}'}), 404
    try:
        pid = info['id']
        pl = req.get(f'https://api.deezer.com/playlist/{pid}', timeout=10).json()
        tracks = req.get(f'https://api.deezer.com/playlist/{pid}/tracks?limit=50', timeout=10).json()
        return jsonify({
            'playlist': norm_playlist(pl),
            'tracks': [norm_track(t) for t in tracks.get('data', [])],
            'country': country.lower(),
            'name': info['name'],
            'flag': info['flag'],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chart_countries')
def chart_countries():
    return jsonify(CHART_PLAYLISTS)

@app.route('/api/download_album', methods=['POST'])
def download_album():
    data = request.json
    album_id = data.get('album_id')
    artist_name = data.get('artist_name', 'Unknown')
    album_title = data.get('album_title', 'Unknown Album')
    if not album_id:
        return jsonify({'error': 'album_id required'}), 400
    bid = str(len(downloads) + 1)
    safe_artist = "".join(c for c in artist_name if c.isalnum() or c in ' -_&').strip()
    safe_album = "".join(c for c in album_title if c.isalnum() or c in ' -_&').strip()
    folder_name = f"{safe_artist} - {safe_album}"
    dest = os.path.join(DOWNLOAD_DIR, folder_name)
    os.makedirs(dest, exist_ok=True)
    downloads[bid] = {'status': 'downloading', 'title': f'Album: {folder_name}', 'progress': 0}
    def run():
        dz = get_dz()
        if not dz.logged_in:
            downloads[bid].update(status='error', error='Login fallito')
            return
        try:
            tracks_resp = req.get(f'https://api.deezer.com/album/{album_id}/tracks', timeout=10).json()
            track_list = tracks_resp.get('data', [])
            total = len(track_list)
            downloads[bid]['total'] = total
            downloads[bid]['completed'] = 0
            for i, t in enumerate(track_list):
                tid = t['id']
                title = t.get('title', f'Track {i+1}')
                safe_title = "".join(c for c in title if c.isalnum() or c in ' -_&').strip()
                filename = f"{i+1:02d} - {safe_title}.mp3"
                dest_path = os.path.join(dest, filename)
                if os.path.exists(dest_path):
                    downloads[bid]['completed'] = i + 1
                    downloads[bid]['progress'] = int((i + 1) / total * 100)
                    continue
                settings = DEFAULTS.copy()
                settings['downloadLocation'] = dest
                try:
                    obj = generateDownloadObject(dz, f'https://www.deezer.com/track/{tid}', settings)
                    obj.bitrate = 1
                    Downloader(dz, obj, settings).start()
                except:
                    pass
                downloads[bid]['completed'] = i + 1
                downloads[bid]['progress'] = int((i + 1) / total * 100)
            downloads[bid].update(status='done', progress=100)
        except Exception as e:
            downloads[bid].update(status='error', error=str(e))
    threading.Thread(target=run, daemon=True).start()
    return jsonify({'id': bid, 'folder': folder_name})

@app.route('/api/files')
def list_files():
    files = []
    for root, dirs, fnames in os.walk(DOWNLOAD_DIR):
        for f in fnames:
            if f.endswith('.mp3'):
                rel = os.path.relpath(os.path.join(root, f), DOWNLOAD_DIR)
                files.append({'name': rel, 'size': os.path.getsize(os.path.join(root, f))})
    return jsonify(files)

HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>D33Z3R</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg-deep:#0a0a0f;
  --bg-mid:#12121a;
  --surface:rgba(255,255,255,0.04);
  --surface-hover:rgba(255,255,255,0.08);
  --border:rgba(255,255,255,0.06);
  --border-light:rgba(255,255,255,0.1);
  --primary:#A238FF;
  --secondary:#FF2D87;
  --text:#fff;
  --dim:rgba(255,255,255,0.6);
  --muted:rgba(255,255,255,0.35);
  --sidebar-w:260px;
  --player-h:96px;
  --playing-green:#1ed760;
}
html,body{height:100%;background:linear-gradient(180deg,var(--bg-deep),var(--bg-mid));color:var(--text);font-family:'Inter',sans-serif;font-size:14px;overflow:hidden}
a{color:inherit;text-decoration:none}
button{background:none;border:none;color:inherit;cursor:pointer;font:inherit}
input{font:inherit}
::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.1);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:rgba(255,255,255,0.18)}

.app{display:grid;grid-template-columns:var(--sidebar-w) 1fr;grid-template-rows:1fr var(--player-h);height:100vh;overflow:hidden}

/* Sidebar */
.sidebar{grid-row:1;display:flex;flex-direction:column;background:rgba(255,255,255,0.03);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-right:1px solid var(--border);overflow:hidden;z-index:20}
.sidebar-logo{padding:24px 20px 20px;font-family:'Plus Jakarta Sans',sans-serif;font-weight:800;font-size:24px;letter-spacing:2px;background:linear-gradient(135deg,var(--primary),var(--secondary));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;text-shadow:0 0 40px rgba(162,56,255,0.3);cursor:pointer}
.sidebar-search{padding:0 16px 12px}
.sidebar-search input{width:100%;padding:10px 14px;border-radius:10px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-size:13px;outline:none;transition:border-color .2s,background .2s}
.sidebar-search input::placeholder{color:var(--muted)}
.sidebar-search input:focus{border-color:rgba(162,56,255,0.4);background:rgba(255,255,255,0.06)}
.sidebar-nav{padding:8px 8px 4px;display:flex;flex-direction:column;gap:2px}
.nav-item{display:flex;align-items:center;gap:12px;padding:10px 14px;border-radius:10px;color:var(--dim);font-size:13.5px;font-weight:500;cursor:pointer;transition:all .15s;position:relative}
.nav-item:hover{color:var(--text);background:var(--surface-hover)}
.nav-item.active{color:var(--text);background:rgba(162,56,255,0.12)}
.nav-item.active::before{content:'';position:absolute;left:0;top:50%;transform:translateY(-50%);width:3px;height:20px;background:linear-gradient(180deg,var(--primary),var(--secondary));border-radius:0 2px 2px 0}
.nav-item svg{width:18px;height:18px;flex-shrink:0;fill:currentColor;opacity:.85}
.sidebar-divider{height:1px;background:var(--border);margin:8px 16px}
.sidebar-playlists-label{padding:14px 20px 8px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;color:var(--muted)}
.sidebar-playlists{flex:1;overflow-y:auto;padding:0 8px 8px}
.playlist-item{padding:8px 14px;border-radius:8px;font-size:13px;color:var(--dim);cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:all .15s}
.playlist-item:hover{color:var(--text);background:var(--surface-hover)}

/* Main area */
.main{grid-row:1;display:flex;flex-direction:column;overflow:hidden;background:linear-gradient(180deg,var(--bg-deep),var(--bg-mid))}
.content{flex:1;overflow-y:auto;padding:24px 32px 32px}

/* Hero */
.hero{position:relative;border-radius:16px;overflow:hidden;padding:48px 40px;margin-bottom:36px;min-height:200px;background:linear-gradient(135deg,rgba(162,56,255,0.25),rgba(255,45,135,0.18),rgba(10,10,15,0.9))}
.hero::before{content:'';position:absolute;inset:0;background:repeating-conic-gradient(rgba(255,255,255,0.015) 0% 25%,transparent 0% 50%) 0 0/60px 60px;animation:heroPattern 20s linear infinite;pointer-events:none}
@keyframes heroPattern{to{background-position:60px 60px}}
.hero-content{position:relative;z-index:1}
.hero h1{font-family:'Plus Jakarta Sans',sans-serif;font-size:36px;font-weight:800;margin-bottom:8px;background:linear-gradient(135deg,#fff,rgba(255,255,255,0.7));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.hero p{color:var(--dim);font-size:16px;max-width:500px;line-height:1.5}

/* Section */
.section{margin-bottom:36px}
.section-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.section-title{font-family:'Plus Jakarta Sans',sans-serif;font-size:22px;font-weight:700}
.section-more{color:var(--dim);font-size:13px;cursor:pointer;transition:color .15s}
.section-more:hover{color:var(--text)}

/* Charts row */
.charts-row{display:flex;gap:14px;overflow-x:auto;padding-bottom:8px;scroll-snap-type:x mandatory}
.charts-row::-webkit-scrollbar{height:4px}
.chart-card{flex:0 0 160px;border-radius:12px;padding:20px 16px;cursor:pointer;transition:all .25s;scroll-snap-align:start;border:1px solid var(--border);background:var(--surface);position:relative;overflow:hidden}
.chart-card:hover{transform:translateY(-4px);border-color:rgba(162,56,255,0.3);box-shadow:0 12px 40px rgba(162,56,255,0.15)}
.chart-card .flag{font-size:32px;margin-bottom:10px;display:block}
.chart-card .name{font-size:14px;font-weight:600;color:var(--text)}
.chart-card .sub{font-size:11px;color:var(--muted);margin-top:4px}

/* Grid */
.grid-playlists,.grid-albums{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px}
.card{border-radius:12px;padding:14px;cursor:pointer;transition:all .25s;border:1px solid transparent;background:var(--surface)}
.card:hover{transform:translateY(-4px);border-color:var(--border-light);box-shadow:0 12px 40px rgba(0,0,0,0.4)}
.card-img{width:100%;aspect-ratio:1;border-radius:8px;object-fit:cover;background:rgba(255,255,255,0.05);margin-bottom:10px}
.card-title{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card-sub{font-size:12px;color:var(--dim);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* Track list */
.track-list{width:100%}
.track-row{display:grid;grid-template-columns:36px 48px 1fr 1fr 60px 40px;align-items:center;gap:12px;padding:8px 12px;border-radius:8px;transition:background .15s;cursor:pointer}
.track-row:hover{background:var(--surface-hover)}
.track-row.playing{background:rgba(30,215,96,0.08)}
.track-row.playing .track-num{color:var(--playing-green)}
.track-num{font-size:14px;color:var(--muted);text-align:center;font-variant-numeric:tabular-nums}
.track-cover{width:40px;height:40px;border-radius:6px;object-fit:cover;background:rgba(255,255,255,0.05)}
.track-info{overflow:hidden}
.track-title{font-size:14px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.track-artist{font-size:12px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.track-duration{font-size:12px;color:var(--dim);text-align:right;font-variant-numeric:tabular-nums}
.track-dl{width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:6px;transition:all .15s}
.track-dl:hover{background:var(--surface-hover)}
.track-dl svg{width:16px;height:16px;fill:var(--dim)}

/* Player bar */
.player{grid-column:2;display:flex;align-items:center;gap:16px;padding:0 20px;background:rgba(255,255,255,0.03);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-top:1px solid var(--border);height:var(--player-h);z-index:20}
.player-cover{width:64px;height:64px;border-radius:10px;object-fit:cover;background:rgba(255,255,255,0.05);flex-shrink:0}
.player-info{min-width:0;flex:0 0 180px}
.player-title{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer}
.player-title:hover{text-decoration:underline}
.player-artist{font-size:12px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer}
.player-artist:hover{color:var(--text);text-decoration:underline}
.player-center{display:flex;flex-direction:column;align-items:center;gap:6px;flex:1;max-width:600px}
.player-controls{display:flex;align-items:center;gap:16px}
.player-controls button{width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:50%;transition:all .15s}
.player-controls button:hover{background:var(--surface-hover)}
.player-controls button.active{color:var(--primary)}
.player-controls button svg{width:18px;height:18px;fill:currentColor}
.play-btn{width:40px!important;height:40px!important;background:var(--text)!important;color:var(--bg-deep)!important;border-radius:50%!important}
.play-btn:hover{transform:scale(1.06);background:#fff!important}
.play-btn svg{width:20px;height:20px!important;fill:var(--bg-deep)!important}
.progress-wrap{display:flex;align-items:center;gap:8px;width:100%}
.progress-time{font-size:11px;color:var(--muted);min-width:36px;text-align:center;font-variant-numeric:tabular-nums}
.progress-bar{flex:1;height:4px;background:rgba(255,255,255,0.1);border-radius:2px;cursor:pointer;position:relative}
.progress-fill{height:100%;border-radius:2px;background:linear-gradient(90deg,var(--primary),var(--secondary));position:relative;transition:width .1s linear}
.progress-bar:hover .progress-fill{height:6px;margin-top:-1px}
.progress-bar:hover .progress-thumb{opacity:1}
.progress-thumb{width:12px;height:12px;border-radius:50%;background:#fff;position:absolute;right:-6px;top:50%;transform:translateY(-50%);opacity:0;transition:opacity .15s;pointer-events:none;box-shadow:0 0 6px rgba(0,0,0,0.3)}
.player-right{display:flex;align-items:center;gap:12px;flex:0 0 200px;justify-content:flex-end}
.vol-wrap{display:flex;align-items:center;gap:6px}
.vol-wrap button svg{width:18px;height:18px;fill:currentColor}
.vol-bar{width:90px;height:4px;background:rgba(255,255,255,0.1);border-radius:2px;cursor:pointer;position:relative}
.vol-fill{height:100%;border-radius:2px;background:linear-gradient(90deg,var(--primary),var(--secondary));position:relative}
.player-right .icon-btn{width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:6px;transition:all .15s}
.player-right .icon-btn:hover{background:var(--surface-hover)}
.player-right .icon-btn svg{width:18px;height:18px;fill:currentColor}

/* Queue panel */
.queue-panel{position:fixed;right:0;top:0;bottom:var(--player-h);width:360px;background:rgba(18,18,26,0.95);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-left:1px solid var(--border);z-index:30;transform:translateX(100%);transition:transform .3s ease;display:flex;flex-direction:column}
.queue-panel.open{transform:translateX(0)}
.queue-header{display:flex;align-items:center;justify-content:space-between;padding:20px;border-bottom:1px solid var(--border)}
.queue-header h3{font-family:'Plus Jakarta Sans',sans-serif;font-size:18px;font-weight:700}
.queue-close{width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:8px;transition:background .15s}
.queue-close:hover{background:var(--surface-hover)}
.queue-close svg{width:18px;height:18px;fill:currentColor}
.queue-list{flex:1;overflow-y:auto;padding:8px}
.queue-track{display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:8px;cursor:pointer;transition:background .15s}
.queue-track:hover{background:var(--surface-hover)}
.queue-track.active{background:rgba(162,56,255,0.12)}
.queue-track-cover{width:40px;height:40px;border-radius:6px;object-fit:cover;background:rgba(255,255,255,0.05);flex-shrink:0}
.queue-track-info{overflow:hidden;flex:1}
.queue-track-title{font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.queue-track-artist{font-size:11px;color:var(--dim)}

/* Chart header */
.chart-header{display:flex;align-items:flex-end;gap:24px;margin-bottom:32px;padding:32px 0}
.chart-banner{width:200px;height:200px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:80px;background:linear-gradient(135deg,rgba(162,56,255,0.2),rgba(255,45,135,0.15));border:1px solid var(--border)}
.chart-meta h1{font-family:'Plus Jakarta Sans',sans-serif;font-size:32px;font-weight:800;margin-bottom:8px}
.chart-meta p{color:var(--dim);font-size:14px}
.chart-actions{display:flex;gap:10px;margin-top:16px}

/* Album header */
.album-header{display:flex;gap:28px;margin-bottom:32px;padding:32px 0}
.album-cover{width:230px;height:230px;border-radius:12px;object-fit:cover;background:rgba(255,255,255,0.05);flex-shrink:0}
.album-meta{display:flex;flex-direction:column;justify-content:flex-end}
.album-meta .label{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:var(--dim);margin-bottom:6px}
.album-meta h1{font-family:'Plus Jakarta Sans',sans-serif;font-size:36px;font-weight:800;margin-bottom:8px;line-height:1.1}
.album-meta .info{color:var(--dim);font-size:14px}
.album-actions{display:flex;gap:10px;margin-top:16px}

/* Artist page */
.artist-header{display:flex;flex-direction:column;align-items:center;text-align:center;padding:40px 0 32px}
.artist-avatar{width:200px;height:200px;border-radius:50%;object-fit:cover;background:rgba(255,255,255,0.05);margin-bottom:20px;border:3px solid var(--border)}
.artist-header h1{font-family:'Plus Jakarta Sans',sans-serif;font-size:36px;font-weight:800;margin-bottom:8px}
.artist-stats{color:var(--dim);font-size:14px;margin-bottom:20px}
.artist-actions{display:flex;gap:10px}

/* Buttons */
.btn{display:inline-flex;align-items:center;gap:8px;padding:10px 24px;border-radius:50px;font-size:14px;font-weight:600;transition:all .2s;border:none;cursor:pointer}
.btn-primary{background:linear-gradient(135deg,var(--primary),var(--secondary));color:#fff}
.btn-primary:hover{transform:scale(1.03);box-shadow:0 6px 24px rgba(162,56,255,0.3)}
.btn-outline{background:transparent;border:1px solid var(--border-light);color:var(--text)}
.btn-outline:hover{background:var(--surface-hover);border-color:rgba(255,255,255,0.2)}
.btn-sm{padding:8px 18px;font-size:13px}
.btn svg{width:16px;height:16px;fill:currentColor}

/* Toast */
.toast{position:fixed;bottom:calc(var(--player-h) + 20px);left:50%;transform:translateX(-50%) translateY(80px);background:rgba(30,30,40,0.95);backdrop-filter:blur(10px);color:var(--text);padding:12px 24px;border-radius:10px;font-size:13px;font-weight:500;z-index:100;border:1px solid var(--border);transition:transform .3s ease,opacity .3s ease;opacity:0;pointer-events:none}
.toast.show{transform:translateX(-50%) translateY(0);opacity:1}

/* Loading */
.loading-overlay{position:fixed;inset:0;background:rgba(10,10,15,0.7);display:flex;align-items:center;justify-content:center;z-index:200;opacity:0;pointer-events:none;transition:opacity .2s}
.loading-overlay.show{opacity:1;pointer-events:auto}
.loading-spinner{width:40px;height:40px;border:3px solid rgba(255,255,255,0.1);border-top-color:var(--primary);border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

/* Equalizer */
.equalizer{display:flex;align-items:flex-end;gap:2px;height:16px}
.eq-bar{width:3px;background:var(--playing-green);border-radius:1px;animation:eqBounce .6s ease-in-out infinite alternate}
.eq-bar:nth-child(1){height:8px;animation-delay:0s}
.eq-bar:nth-child(2){height:14px;animation-delay:.15s}
.eq-bar:nth-child(3){height:6px;animation-delay:.3s}
.eq-bar:nth-child(4){height:12px;animation-delay:.1s}
.eq-bar:nth-child(5){height:9px;animation-delay:.25s}
@keyframes eqBounce{0%{height:4px}100%{height:16px}}

/* Search results */
.search-section{margin-bottom:28px}
.search-section h3{font-family:'Plus Jakarta Sans',sans-serif;font-size:18px;font-weight:700;margin-bottom:12px}
.results-artists{display:flex;gap:14px;overflow-x:auto;padding-bottom:8px}
.artist-card{flex:0 0 140px;text-align:center;cursor:pointer;transition:all .2s;padding:12px;border-radius:12px}
.artist-card:hover{background:var(--surface-hover)}
.artist-card img{width:100px;height:100px;border-radius:50%;object-fit:cover;margin:0 auto 10px;display:block;background:rgba(255,255,255,0.05)}
.artist-card .name{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.artist-card .sub{font-size:11px;color:var(--dim)}

/* Library */
.library-list{display:flex;flex-direction:column;gap:2px}
.library-item{display:flex;align-items:center;gap:12px;padding:10px 14px;border-radius:8px;cursor:pointer;transition:background .15s}
.library-item:hover{background:var(--surface-hover)}
.library-item.playing{background:rgba(30,215,96,0.08)}
.library-icon{width:36px;height:36px;display:flex;align-items:center;justify-content:center;border-radius:8px;background:rgba(255,255,255,0.05);flex-shrink:0}
.library-icon svg{width:16px;height:16px;fill:var(--dim)}
.library-info{overflow:hidden;flex:1}
.library-name{font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.library-size{font-size:11px;color:var(--muted)}
.library-play{width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:50%;opacity:0;transition:opacity .15s}
.library-item:hover .library-play{opacity:1}
.library-play svg{width:14px;height:14px;fill:var(--text)}

/* Settings */
.settings-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:24px;display:flex;flex-direction:column;gap:16px}
.settings-row{display:flex;flex-direction:column;gap:4px}
.settings-row label{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;color:var(--muted)}
.settings-val{font-size:14px;color:var(--text);word-break:break-all;padding:10px 14px;background:var(--bg);border-radius:8px;border:1px solid var(--border);font-family:'SF Mono','Fira Code',monospace}
.settings-arl{font-size:12px;max-height:80px;overflow-y:auto}
.settings-actions{margin-top:8px}
.btn-primary{padding:10px 24px;border:none;border-radius:8px;background:linear-gradient(135deg,var(--primary),var(--secondary));color:#fff;font-size:14px;font-weight:600;cursor:pointer;transition:all .2s}
.btn-primary:hover{transform:translateY(-1px);box-shadow:0 4px 20px rgba(162,56,255,0.3)}
.btn-primary:active{transform:translateY(0)}
.arl-verbose{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:12px;max-height:200px;overflow-y:auto;margin-top:8px;font-family:'SF Mono','Fira Code',monospace;font-size:12px;line-height:1.6}
.arl-entry{color:var(--dim)}
.arl-success{color:var(--accent)}
.arl-warn{color:#f0ad4e}
.arl-error{color:#ff4444}
.arl-verbose code{word-break:break-all;font-size:11px;color:var(--text)}
.arl-progress{height:4px;background:var(--surface3);border-radius:2px;margin-top:8px;overflow:hidden}
.arl-progress-fill{height:100%;background:linear-gradient(90deg,var(--primary),var(--secondary));border-radius:2px;transition:width .3s}

/* View sections */
.view-section{display:none}
.view-section.active{display:block}

/* Responsive */
@media(max-width:900px){
  .app{grid-template-columns:1fr}
  .sidebar{display:none}
  .player{grid-column:1}
  .track-row{grid-template-columns:36px 40px 1fr 60px 36px}
  .track-row .track-artist-col{display:none}
}
</style>
</head>
<body>
<div class="app">
  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="sidebar-logo" onclick="navTo('home')">D33Z3R</div>
    <div class="sidebar-search">
      <input type="text" id="searchInput" placeholder="Cerca..." oninput="onSearchInput(this.value)">
    </div>
    <nav class="sidebar-nav">
      <div class="nav-item active" data-view="home" onclick="navTo('home')">
        <svg viewBox="0 0 24 24"><path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>
        Home
      </div>
      <div class="nav-item" data-view="charts" onclick="navTo('charts')">
        <svg viewBox="0 0 24 24"><path d="M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z"/></svg>
        Top 50 Charts
      </div>
      <div class="nav-item" data-view="momento" onclick="navTo('momento')">
        <svg viewBox="0 0 24 24"><path d="M13.5.67s.74 2.65.74 4.8c0 2.06-1.35 3.73-3.41 3.73-2.07 0-3.63-1.67-3.63-3.73l.03-.36C5.21 7.51 4 10.62 4 14c0 4.42 3.58 8 8 8s8-3.58 8-8C20 8.61 17.41 3.8 13.5.67z"/></svg>
        Del Momento
      </div>
      <div class="nav-item" data-view="novita" onclick="navTo('novita')">
        <svg viewBox="0 0 24 24"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55C7.79 13 6 14.79 6 17s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>
        Novità
      </div>
      <div class="nav-item" data-view="search" onclick="navTo('search')">
        <svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
        Cerca
      </div>
      <div class="nav-item" data-view="library" onclick="navTo('library')">
        <svg viewBox="0 0 24 24"><path d="M20 2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 5h-3v5.5a2.5 2.5 0 01-5 0 2.5 2.5 0 012.5-2.5c.57 0 1.08.19 1.5.51V5h4v2zM4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6z"/></svg>
        Libreria
      </div>
      <div class="nav-item" data-view="settings" onclick="navTo('settings')">
        <svg viewBox="0 0 24 24"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 00.12-.61l-1.92-3.32a.488.488 0 00-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 00-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58a.49.49 0 00-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg>
        Impostazioni
      </div>
    </nav>
    <div class="sidebar-divider"></div>
    <div class="sidebar-playlists-label">Playlist</div>
    <div class="sidebar-playlists" id="sidebarPlaylists"></div>
  </aside>

  <!-- Main -->
  <main class="main">
    <div class="content" id="content">
      <!-- Views injected here -->
    </div>
  </main>

  <!-- Player Bar -->
  <div class="player" id="playerBar">
    <img class="player-cover" id="playerCover" src="" alt="">
    <div class="player-info">
      <div class="player-title" id="playerTitle" onclick="openCurrentArtist()"></div>
      <div class="player-artist" id="playerArtist" onclick="openCurrentArtist()"></div>
    </div>
    <div class="player-center">
      <div class="player-controls">
        <button id="btnShuffle" onclick="toggleShuffle()" title="Shuffle">
          <svg viewBox="0 0 24 24"><path d="M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z"/></svg>
        </button>
        <button onclick="prevTrack()" title="Precedente">
          <svg viewBox="0 0 24 24"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg>
        </button>
        <button class="play-btn" id="btnPlay" onclick="togglePlay()" title="Play/Pausa">
          <svg id="iconPlay" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
          <svg id="iconPause" viewBox="0 0 24 24" style="display:none"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
        </button>
        <button onclick="nextTrack()" title="Successivo">
          <svg viewBox="0 0 24 24"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
        </button>
        <button id="btnRepeat" onclick="toggleRepeat()" title="Ripeti">
          <svg viewBox="0 0 24 24"><path d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z"/></svg>
        </button>
      </div>
      <div class="progress-wrap">
        <span class="progress-time" id="currentTime">0:00</span>
        <div class="progress-bar" id="progressBar">
          <div class="progress-fill" id="progressFill" style="width:0%">
            <div class="progress-thumb"></div>
          </div>
        </div>
        <span class="progress-time" id="totalTime">0:00</span>
      </div>
    </div>
    <div class="player-right">
      <div class="vol-wrap">
        <button onclick="toggleMute()" id="volIcon">
          <svg viewBox="0 0 24 24"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg>
        </button>
        <div class="vol-bar" id="volBar">
          <div class="vol-fill" id="volFill" style="width:80%"></div>
        </div>
      </div>
      <button class="icon-btn" onclick="downloadCurrent()" title="Scarica">
        <svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
      </button>
      <button class="icon-btn" onclick="toggleQueue()" title="Coda">
        <svg viewBox="0 0 24 24"><path d="M15 6H3v2h12V6zm0 4H3v2h12v-2zM3 16h8v-2H3v2zM17 6v8.18c-.31-.11-.65-.18-1-.18-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3V8h3V6h-5z"/></svg>
      </button>
      <div class="equalizer" id="equalizer" style="display:none">
        <div class="eq-bar"></div><div class="eq-bar"></div><div class="eq-bar"></div><div class="eq-bar"></div><div class="eq-bar"></div>
      </div>
    </div>
  </div>
</div>

<!-- Queue Panel -->
<div class="queue-panel" id="queuePanel">
  <div class="queue-header">
    <h3>Coda di riproduzione</h3>
    <button class="queue-close" onclick="toggleQueue()">
      <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
    </button>
  </div>
  <div class="queue-list" id="queueList"></div>
</div>

<!-- Toast -->
<div class="toast" id="toast"></div>

<!-- Loading -->
<div class="loading-overlay" id="loadingOverlay">
  <div class="loading-spinner"></div>
</div>

<audio id="audio" preload="auto"></audio>

<script>
(function(){
"use strict";

const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const audio = $("#audio");
const content = $("#content");

let currentView = "home";
let currentTrackList = [];
let currentTrackIdx = -1;
let isPlaying = false;
let shuffleOn = false;
let repeatOn = false;
let queueOpen = false;
let searchTimeout = null;
let volBeforeMute = 0.8;

function fmt(s){
  if(!s || isNaN(s)) return "0:00";
  const m = Math.floor(s/60);
  const sec = Math.floor(s%60);
  return m+":"+(sec<10?"0":"")+sec;
}

function toast(msg){
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._tid);
  t._tid = setTimeout(()=> t.classList.remove("show"),2500);
}

function loading(show){
  $("#loadingOverlay").classList.toggle("show",!!show);
}

function setPlayIcon(playing){
  $("#iconPlay").style.display = playing?"none":"block";
  $("#iconPause").style.display = playing?"block":"none";
  isPlaying = playing;
  $("#equalizer").style.display = playing?"flex":"none";
}

function updatePlayerUI(t){
  if(!t) return;
  $("#playerCover").src = proxyImg(t.cover || "");
  $("#playerTitle").textContent = t.title || "";
  $("#playerArtist").textContent = t.artist || "";
}

function openCurrentArtist(){
  if(currentTrackIdx>=0 && currentTrackList[currentTrackIdx]){
    const t = currentTrackList[currentTrackIdx];
    if(t.artist_id) openArtist(t.artist_id);
  }
}

function playTrack(track,list,idx){
  currentTrackList = list || [track];
  currentTrackIdx = idx!==undefined ? idx : 0;
  updatePlayerUI(track);
  let url = track.id ? "/api/stream_track/"+track.id : "";
  if(track.local) url = "/api/stream/"+encodeURIComponent(track.name);
  if(track.preview_url) url = track.preview_url;
  if(!url){
    toast("Nessuna fonte audio disponibile");
    return;
  }
  audio.src = url;
  audio.load();
  let playPromise = audio.play();
  if(playPromise !== undefined){
    playPromise.catch(()=>{
      // Firefox autoplay blocked — try muted first then unmute
      audio.muted = true;
      audio.play().then(()=>{
        audio.muted = false;
        updatePlayingState();
      }).catch(()=> fallbackToPreview(track));
    });
  }
  updatePlayingState();
}

function fallbackToPreview(t){
  if(t && t.preview_url){
    audio.src = t.preview_url;
    audio.load();
    audio.play().catch(()=> toast("Errore di riproduzione"));
  }
}

function togglePlay(){
  if(!audio.src) return;
  if(audio.paused) audio.play();
  else audio.pause();
}

function prevTrack(){
  if(currentTrackIdx > 0){
    currentTrackIdx--;
    playTrack(currentTrackList[currentTrackIdx],currentTrackList,currentTrackIdx);
  }
}

function nextTrack(){
  if(shuffleOn){
    let next = Math.floor(Math.random()*currentTrackList.length);
    playTrack(currentTrackList[next],currentTrackList,next);
  } else if(currentTrackIdx < currentTrackList.length-1){
    currentTrackIdx++;
    playTrack(currentTrackList[currentTrackIdx],currentTrackList,currentTrackIdx);
  } else if(repeatOn){
    currentTrackIdx = 0;
    playTrack(currentTrackList[0],currentTrackList,0);
  }
}

function toggleShuffle(){
  shuffleOn = !shuffleOn;
  $("#btnShuffle").classList.toggle("active",shuffleOn);
  toast(shuffleOn?"Shuffle attivato":"Shuffle disattivato");
}

function toggleRepeat(){
  repeatOn = !repeatOn;
  $("#btnRepeat").classList.toggle("active",repeatOn);
  toast(repeatOn?"Ripeti attivato":"Ripeti disattivato");
}

function toggleMute(){
  if(audio.volume > 0){
    volBeforeMute = audio.volume;
    audio.volume = 0;
    $("#volFill").style.width = "0%";
    updateVolIcon(0);
  } else {
    audio.volume = volBeforeMute;
    $("#volFill").style.width = (volBeforeMute*100)+"%";
    updateVolIcon(volBeforeMute);
  }
}

function updateVolIcon(v){
  const paths = [
    "M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z",
    "M18.5 12c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM5 9v6h4l5 5V4L9 9H5z",
    "M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"
  ];
  const el = $("#volIcon");
  if(v===0) el.innerHTML = '<svg viewBox="0 0 24 24"><path d="'+paths[0]+'"/><line x1="23" y1="9" x2="17" y2="15" stroke="currentColor" stroke-width="2"/><line x1="17" y1="9" x2="23" y2="15" stroke="currentColor" stroke-width="2"/></svg>';
  else if(v<0.5) el.innerHTML = '<svg viewBox="0 0 24 24"><path d="'+paths[1]+'"/></svg>';
  else el.innerHTML = '<svg viewBox="0 0 24 24"><path d="'+paths[2]+'"/></svg>';
}

audio.ontimeupdate = function(){
  if(!audio.duration) return;
  const pct = (audio.currentTime/audio.duration)*100;
  $("#progressFill").style.width = pct+"%";
  $("#currentTime").textContent = fmt(audio.currentTime);
  $("#totalTime").textContent = fmt(audio.duration);
};

audio.onended = function(){
  nextTrack();
};

audio.onplay = function(){ setPlayIcon(true); };
audio.onpause = function(){ setPlayIcon(false); };

function updatePlayingState(){
  $$(".track-row").forEach(r=>{
    const idx = parseInt(r.dataset.idx);
    r.classList.toggle("playing", idx===currentTrackIdx && currentTrackList===window._lastTrackList);
  });
}

function trackRowHtml(t,i,tracks){
  const isCurrent = window._lastTrackList===tracks && i===currentTrackIdx;
  return '<div class="track-row'+(isCurrent?" playing":"")+'" data-idx="'+i+'" onclick="window._playFromRow('+i+')">' +
    '<span class="track-num">'+(isCurrent&&isPlaying?'<div class="equalizer" style="display:flex"><div class="eq-bar"></div><div class="eq-bar"></div><div class="eq-bar"></div><div class="eq-bar"></div><div class="eq-bar"></div></div>':(i+1))+'</span>' +
    '<img class="track-cover" src="'+proxyImg(t.cover)+'" alt="">' +
    '<div class="track-info"><div class="track-title">'+esc(t.title||'')+'</div><div class="track-artist">'+esc(t.artist||'')+'</div></div>' +
    '<span class="track-duration">'+fmt(t.duration)+'</span>' +
    '<button class="track-dl" onclick="event.stopPropagation();downloadTrack(\''+t.id+'\',\''+esc(t.title||'')+'\')" title="Scarica"><svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg></button>' +
  '</div>';
}

function esc(s){ return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;"); }
function proxyImg(u){ return u ? '/api/proxy_image?url='+encodeURIComponent(u) : ''; }

function renderTracksHtml(tracks,title){
  window._lastTrackList = tracks;
  let html = '<div class="track-list">';
  tracks.forEach((t,i)=> html += trackRowHtml(t,i,tracks));
  html += '</div>';
  return html;
}

function bindTrackRows(){
  window._playFromRow = function(i){
    playTrack(window._lastTrackList[i], window._lastTrackList, i);
  };
}

function navTo(view){
  currentView = view;
  $$(".nav-item").forEach(n=> n.classList.toggle("active", n.dataset.view===view));
  if(view==="home") loadHome();
  else if(view==="charts") loadChart("worldwide");
  else if(view==="momento") loadMomento();
  else if(view==="novita") loadNewReleases();
  else if(view==="search") content.innerHTML = '<div style="text-align:center;padding:60px 0;color:var(--muted)"><p style="font-size:16px">Usa la barra di ricerca nella sidebar</p></div>';
  else if(view==="library") loadFiles();
  else if(view==="settings") loadSettings();
}

async function loadHome(){
  loading(true);
  try{
    const r = await fetch("/api/trending");
    const d = await r.json();
    let html = '';
    html += '<div class="hero"><div class="hero-content"><h1>Ciao, bentornato su D33Z3R</h1><p>Scopri la musica che ama il mondo. Ascolta ora.</p></div></div>';
    html += '<div class="section"><div class="section-header"><span class="section-title">Top 50 Charts</span></div>';
    html += '<div class="charts-row">';
    const countries = [
      {code:"worldwide",flag:"🌍",name:"Worldwide"},
      {code:"italy",flag:"🇮🇹",name:"Italia"},
      {code:"france",flag:"🇫🇷",name:"Francia"},
      {code:"usa",flag:"🇺🇸",name:"USA"},
      {code:"uk",flag:"🇬🇧",name:"Regno Unito"},
      {code:"germany",flag:"🇩🇪",name:"Germania"},
      {code:"spain",flag:"🇪🇸",name:"Spagna"},
      {code:"brazil",flag:"🇧🇷",name:"Brasile"},
      {code:"japan",flag:"🇯🇵",name:"Giappone"}
    ];
    countries.forEach(c=> {
      html += '<div class="chart-card" onclick="loadChart(\''+c.code+'\')"><span class="flag">'+c.flag+'</span><div class="name">'+c.name+'</div><div class="sub">Top 50</div></div>';
    });
    html += '</div></div>';
    if(d.chart_playlists && d.chart_playlists.length){
      html += '<div class="section"><div class="section-header"><span class="section-title">Playlist del momento</span></div><div class="grid-playlists">';
      d.chart_playlists.slice(0,8).forEach(p=>{
        html += '<div class="card" onclick="openPlaylist(\''+p.id+'\')"><img class="card-img" src="'+proxyImg(p.image)+'" alt=""><div class="card-title">'+esc(p.name)+'</div><div class="card-sub">'+esc(p.owner||'')+'</div></div>';
      });
      html += '</div></div>';
    }
    if(d.chart_albums && d.chart_albums.length){
      html += '<div class="section"><div class="section-header"><span class="section-title">Album del momento</span></div><div class="grid-albums">';
      d.chart_albums.slice(0,8).forEach(a=>{
        html += '<div class="card" onclick="openAlbum(\''+a.id+'\')"><img class="card-img" src="'+proxyImg(a.cover)+'" alt=""><div class="card-title">'+esc(a.title)+'</div><div class="card-sub">'+esc(a.artist||'')+'</div></div>';
      });
      html += '</div></div>';
    }
    if(d.chart_tracks && d.chart_tracks.length){
      html += '<div class="section"><div class="section-header"><span class="section-title">Classifica</span><span class="section-more" onclick="loadChart(\'worldwide\')">Vedi tutto</span></div>';
      html += renderTracksHtml(d.chart_tracks.slice(0,20));
      html += '</div>';
    }
    if(d.new_releases && d.new_releases.length){
      html += '<div class="section"><div class="section-header"><span class="section-title">Novità</span><span class="section-more" onclick="loadNewReleases()">Vedi tutto</span></div><div class="grid-albums">';
      d.new_releases.slice(0,8).forEach(a=>{
        html += '<div class="card" onclick="openAlbum(\''+a.id+'\')"><img class="card-img" src="'+proxyImg(a.cover)+'" alt=""><div class="card-title">'+esc(a.title)+'</div><div class="card-sub">'+esc(a.artist||'')+'</div></div>';
      });
      html += '</div></div>';
    }
    content.innerHTML = html;
    bindTrackRows();
  }catch(e){
    content.innerHTML = '<div style="text-align:center;padding:60px;color:var(--dim)">Errore nel caricamento</div>';
  }
  loading(false);
}

async function loadChart(country){
  loading(true);
  try{
    const r = await fetch("/api/chart/"+country);
    const d = await r.json();
    let html = '<div class="chart-header">';
    html += '<div class="chart-banner">'+(d.flag||"🎵")+'</div>';
    html += '<div class="chart-meta"><h1>Top 50 '+(d.name||country)+'</h1>';
    html += '<p>'+(d.playlist?d.playlist.description||'':'Classifica')+'</p>';
    html += '<div class="chart-actions">';
    html += '<button class="btn btn-primary" onclick="playAllFromList()"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> Riproduci tutto</button>';
    html += '<button class="btn btn-outline" onclick="downloadPlaylistTracks(window._chartTrackIds)"><svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg> Scarica tutto</button>';
    html += '</div></div></div>';
    window._chartTrackIds = (d.tracks||[]).map(t=>t.id);
    html += renderTracksHtml(d.tracks||[]);
    content.innerHTML = html;
    bindTrackRows();
  }catch(e){
    content.innerHTML = '<div style="text-align:center;padding:60px;color:var(--dim)">Errore nel caricamento della classifica</div>';
  }
  loading(false);
}

async function loadNewReleases(){
  loading(true);
  try{
    const r = await fetch("/api/new_releases");
    const d = await r.json();
    let html = '<div class="section"><div class="section-header"><span class="section-title">Novità</span></div><div class="grid-albums">';
    (d.albums||[]).forEach(a=>{
      html += '<div class="card" onclick="openAlbum(\''+a.id+'\')"><img class="card-img" src="'+proxyImg(a.cover)+'" alt=""><div class="card-title">'+esc(a.title)+'</div><div class="card-sub">'+esc(a.artist||'')+'</div></div>';
    });
    html += '</div></div>';
    content.innerHTML = html;
  }catch(e){
    content.innerHTML = '<div style="text-align:center;padding:60px;color:var(--dim)">Errore nel caricamento</div>';
  }
  loading(false);
}

async function loadMomento(){
  loading(true);
  try{
    const r = await fetch("/api/trending");
    const d = await r.json();
    let html = '<div class="section"><div class="section-header"><span class="section-title">Playlist del momento</span></div><div class="grid-playlists">';
    (d.chart_playlists||[]).forEach(p=>{
      html += '<div class="card" onclick="openPlaylist(\''+p.id+'\')"><img class="card-img" src="'+proxyImg(p.image)+'" alt=""><div class="card-title">'+esc(p.name)+'</div><div class="card-sub">'+esc(p.owner||'')+'</div></div>';
    });
    html += '</div></div>';
    html += '<div class="section"><div class="section-header"><span class="section-title">Album del momento</span></div><div class="grid-albums">';
    (d.chart_albums||[]).forEach(a=>{
      html += '<div class="card" onclick="openAlbum(\''+a.id+'\')"><img class="card-img" src="'+proxyImg(a.cover)+'" alt=""><div class="card-title">'+esc(a.title)+'</div><div class="card-sub">'+esc(a.artist||'')+'</div></div>';
    });
    html += '</div></div>';
    content.innerHTML = html;
  }catch(e){
    content.innerHTML = '<div style="text-align:center;padding:60px;color:var(--dim)">Errore nel caricamento</div>';
  }
  loading(false);
}

async function openPlaylist(id){
  loading(true);
  try{
    const r = await fetch("/api/playlist/"+id);
    const d = await r.json();
    let html = '<div class="album-header">';
    html += '<img class="album-cover" src="'+proxyImg(d.playlist?d.playlist.image:'')+'" alt="">';
    html += '<div class="album-meta"><div class="label">Playlist</div>';
    html += '<h1>'+esc(d.playlist?d.playlist.name:'')+'</h1>';
    html += '<div class="info">'+esc(d.playlist?d.playlist.owner||'':'')+' &middot; '+(d.tracks?d.tracks.length:0)+' brani</div>';
    html += '<div class="album-actions">';
    html += '<button class="btn btn-primary" onclick="playAllFromList()"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> Riproduci tutto</button>';
    html += '<button class="btn btn-outline" onclick="downloadPlaylistTracks(window._listTrackIds)"><svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg> Scarica tutto</button>';
    html += '</div></div></div>';
    window._listTrackIds = (d.tracks||[]).map(t=>t.id);
    html += renderTracksHtml(d.tracks||[]);
    content.innerHTML = html;
    bindTrackRows();
  }catch(e){
    content.innerHTML = '<div style="text-align:center;padding:60px;color:var(--dim)">Errore nel caricamento</div>';
  }
  loading(false);
}

async function openAlbum(id){
  loading(true);
  try{
    const r = await fetch("/api/album/"+id);
    const d = await r.json();
    let html = '<div class="album-header">';
    html += '<img class="album-cover" src="'+proxyImg(d.album?d.album.cover:'')+'" alt="">';
    html += '<div class="album-meta"><div class="label">Album</div>';
    html += '<h1>'+esc(d.album?d.album.title:'')+'</h1>';
    html += '<div class="info">'+esc(d.album?d.album.artist||'':'')+' &middot; '+(d.tracks?d.tracks.length:0)+' brani</div>';
    html += '<div class="album-actions">';
    html += '<button class="btn btn-primary" onclick="playAllFromList()"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> Riproduci tutto</button>';
    html += '<button class="btn btn-outline" onclick="downloadAlbumTracks(\''+id+'\',\''+esc(d.album?d.album.artist||'':'')+'\',\''+esc(d.album?d.album.title||'':'')+'\')"><svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg> Scarica Album</button>';
    html += '</div></div></div>';
    html += renderTracksHtml(d.tracks||[]);
    content.innerHTML = html;
    bindTrackRows();
  }catch(e){
    content.innerHTML = '<div style="text-align:center;padding:60px;color:var(--dim)">Errore nel caricamento</div>';
  }
  loading(false);
}

async function openArtist(id){
  loading(true);
  try{
    const r = await fetch("/api/artist/"+id);
    const d = await r.json();
    let html = '<div class="artist-header">';
    html += '<img class="artist-avatar" src="'+proxyImg(d.artist?d.artist.image:'')+'" alt="">';
    html += '<h1>'+esc(d.artist?d.artist.name:'')+'</h1>';
    const stats = d.artist?(d.artist.followers?d.artist.followers.toLocaleString()+" follower":""):"";
    html += '<div class="artist-stats">'+stats+'</div>';
    html += '</div>';
    if(d.top && d.top.length){
      html += '<div class="section"><div class="section-header"><span class="section-title">Top brani</span></div>';
      html += renderTracksHtml(d.top);
      html += '</div>';
    }
    if(d.albums && d.albums.length){
      html += '<div class="section"><div class="section-header"><span class="section-title">Album</span></div><div class="grid-albums">';
      d.albums.forEach(a=>{
        html += '<div class="card" onclick="openAlbum(\''+a.id+'\')"><img class="card-img" src="'+proxyImg(a.cover)+'" alt=""><div class="card-title">'+esc(a.title)+'</div></div>';
      });
      html += '</div></div>';
    }
    content.innerHTML = html;
    bindTrackRows();
  }catch(e){
    content.innerHTML = '<div style="text-align:center;padding:60px;color:var(--dim)">Errore nel caricamento</div>';
  }
  loading(false);
}

function playAllFromList(){
  if(window._lastTrackList && window._lastTrackList.length){
    playTrack(window._lastTrackList[0], window._lastTrackList, 0);
  }
}

function playAllTracks(){
  playAllFromList();
}

let searchDebounce = null;
function onSearchInput(q){
  clearTimeout(searchDebounce);
  if(!q.trim()){
    if(currentView==="search") content.innerHTML = '<div style="text-align:center;padding:60px 0;color:var(--muted)"><p style="font-size:16px">Usa la barra di ricerca nella sidebar</p></div>';
    return;
  }
  searchDebounce = setTimeout(()=> doSearch(q.trim()), 300);
}

async function doSearch(q){
  loading(true);
  try{
    const r = await fetch("/api/search?q="+encodeURIComponent(q));
    const d = await r.json();
    let html = '<div class="section"><div class="section-title" style="margin-bottom:20px">Risultati per "'+esc(q)+'"</div>';
    if(d.artists && d.artists.length){
      html += '<div class="search-section"><h3>Artisti</h3><div class="results-artists">';
      d.artists.slice(0,10).forEach(a=>{
        html += '<div class="artist-card" onclick="openArtist(\''+a.id+'\')"><img src="'+proxyImg(a.image)+'" alt=""><div class="name">'+esc(a.name)+'</div></div>';
      });
      html += '</div></div>';
    }
    if(d.albums && d.albums.length){
      html += '<div class="search-section"><h3>Album</h3><div class="grid-albums">';
      d.albums.slice(0,12).forEach(a=>{
        html += '<div class="card" onclick="openAlbum(\''+a.id+'\')"><img class="card-img" src="'+proxyImg(a.cover)+'" alt=""><div class="card-title">'+esc(a.title)+'</div><div class="card-sub">'+esc(a.artist||'')+'</div></div>';
      });
      html += '</div></div>';
    }
    if(d.playlists && d.playlists.length){
      html += '<div class="search-section"><h3>Playlist</h3><div class="grid-playlists">';
      d.playlists.slice(0,12).forEach(p=>{
        html += '<div class="card" onclick="openPlaylist(\''+p.id+'\')"><img class="card-img" src="'+proxyImg(p.image)+'" alt=""><div class="card-title">'+esc(p.name)+'</div><div class="card-sub">'+esc(p.owner||'')+'</div></div>';
      });
      html += '</div></div>';
    }
    if(d.tracks && d.tracks.length){
      html += '<div class="search-section"><h3>Brani</h3>';
      html += renderTracksHtml(d.tracks.slice(0,20));
      html += '</div>';
    }
    html += '</div>';
    content.innerHTML = html;
    bindTrackRows();
  }catch(e){
    content.innerHTML = '<div style="text-align:center;padding:60px;color:var(--dim)">Errore nella ricerca</div>';
  }
  loading(false);
}

async function loadFiles(){
  loading(true);
  try{
    const r = await fetch("/api/files");
    const files = await r.json();
    let html = '<div class="section"><div class="section-header"><span class="section-title">Libreria locale</span></div>';
    html += '<div class="library-list">';
    (files||[]).forEach(f=>{
      const name = f.name || "";
      const parts = name.split("/");
      const displayName = parts[parts.length-1];
      const displayDir = parts.length>1 ? parts.slice(0,-1).join(" / ") : "";
      html += '<div class="library-item" onclick="playLocalFile(\''+esc(name)+'\')">';
      html += '<div class="library-icon"><svg viewBox="0 0 24 24"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55C7.79 13 6 14.79 6 17s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg></div>';
      html += '<div class="library-info"><div class="library-name">'+esc(displayName)+'</div>';
      if(displayDir) html += '<div class="library-size">'+esc(displayDir)+'</div>';
      html += '</div>';
      html += '<span class="library-size">'+(f.size?((f.size/1048576).toFixed(1)+" MB"):"")+'</span>';
      html += '<div class="library-play"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></div>';
      html += '</div>';
    });
    html += '</div></div>';
    content.innerHTML = html;
  }catch(e){
    content.innerHTML = '<div style="text-align:center;padding:60px;color:var(--dim)">Errore nel caricamento della libreria</div>';
  }
  loading(false);
}

async function loadSettings(){
  loading(true);
  try{
    const r = await fetch("/api/settings");
    const s = await r.json();
    let html = '<div class="section" style="max-width:600px">';
    html += '<div class="section-header"><span class="section-title">Impostazioni</span></div>';
    html += '<div class="settings-card">';
    html += '<div class="settings-row"><label>Email</label><div class="settings-val" id="setEmail">'+esc(s.email||'Non disponibile')+'</div></div>';
    html += '<div class="settings-row"><label>Password</label><div class="settings-val" id="setPass">'+esc(s.password||'Non disponibile')+'</div></div>';
    html += '<div class="settings-row"><label>ARL</label><div class="settings-val settings-arl" id="setArl">'+esc(s.arl||'Non disponibile')+'</div></div>';
    html += '<div class="settings-row"><label>Data creazione</label><div class="settings-val" id="setCreated">'+esc(s.created ? new Date(s.created).toLocaleString('it-IT') : 'Non disponibile')+'</div></div>';
    html += '<div class="settings-actions">';
    html += '<button class="btn-primary" onclick="generateArl()">Genera nuovo ARL</button>';
    html += '</div>';
    html += '<div id="arlStatus" style="margin-top:12px;font-size:13px;color:var(--dim)"></div>';
    html += '</div></div>';
    content.innerHTML = html;
  }catch(e){
    content.innerHTML = '<div style="text-align:center;padding:60px;color:var(--dim)">Errore nel caricamento delle impostazioni</div>';
  }
  loading(false);
}

async function generateArl(){
  const status = document.getElementById("arlStatus");
  status.innerHTML = '<div class="arl-verbose" id="arlLog"><div class="arl-entry" style="color:var(--accent)">Generazione in corso...</div></div><div class="arl-progress"><div class="arl-progress-fill" id="arlProgressFill" style="width:0%"></div></div>';
  try{
    const r = await fetch("/api/generate_arl", {method:"POST"});
    const d = await r.json();
    const logEl = document.getElementById("arlLog");
    const fillEl = document.getElementById("arlProgressFill");
    const poll = async()=>{
      for(let i=0;i<60;i++){
        await new Promise(r=>setTimeout(r,2000));
        const pr = await fetch("/api/downloads");
        const downloads = await pr.json();
        const dl = downloads[d.id];
        if(!dl) continue;
        if(dl.logs && logEl){
          logEl.innerHTML = dl.logs.map(l=>'<div class="arl-entry">'+esc(l)+'</div>').join('');
          logEl.scrollTop = logEl.scrollHeight;
        }
        if(fillEl) fillEl.style.width = (dl.progress||0)+'%';
        if(dl.status==="done"){
          let result = '<div class="arl-entry arl-success">Account generato con successo!</div>';
          result += '<div class="arl-entry">Inizio: <b>'+esc(dl.start_time||'')+'</b>  Fine: <b>'+esc(dl.end_time||'')+'</b>  Durata: <b>'+esc(dl.elapsed||'')+'</b></div>';
          result += '<div class="arl-entry">Email: <b>'+esc(dl.email||'')+'</b></div>';
          result += '<div class="arl-entry">ARL: <code>'+esc(dl.arl||'')+'</code></div>';
          result += '<div class="arl-entry">Creazione: <b>'+esc(dl.created ? new Date(dl.created).toLocaleString('it-IT') : '')+'</b></div>';
          if(dl.verified) result += '<div class="arl-entry arl-success">Verifica login: OK</div>';
          else result += '<div class="arl-entry arl-warn">Verifica login: non confermato</div>';
          logEl.innerHTML += result;
          document.getElementById("setArl").textContent = dl.arl||"";
          document.getElementById("setEmail").textContent = dl.email||"";
          document.getElementById("setPass").textContent = dl.password||"";
          if(dl.created) document.getElementById("setCreated").textContent = new Date(dl.created).toLocaleString('it-IT');
          return;
        }
        if(dl.status==="error"){
          logEl.innerHTML += '<div class="arl-entry arl-error">ERRORE: '+esc(dl.error||'Errore sconosciuto')+'</div>';
          return;
        }
      }
      logEl.innerHTML += '<div class="arl-entry arl-error">Timeout (120s)</div>';
    };
    poll();
  }catch(e){
    status.innerHTML = '<div class="arl-entry arl-error">Errore di connessione</div>';
  }
}

window.playLocalFile = function(name){
  const track = {name:name, local:true, title:name.split("/").pop(), artist:"Locale"};
  playTrack(track, [track], 0);
};

function toggleQueue(){
  queueOpen = !queueOpen;
  $("#queuePanel").classList.toggle("open", queueOpen);
  if(queueOpen) renderQueue();
}

function renderQueue(){
  let html = '';
  if(currentTrackList.length){
    html += '<div class="queue-track active">';
    html += '<img class="queue-track-cover" src="'+proxyImg(currentTrackIdx>=0&&currentTrackList[currentTrackIdx]?currentTrackList[currentTrackIdx].cover:'')+'" alt="">';
    html += '<div class="queue-track-info"><div class="queue-track-title">'+(currentTrackIdx>=0&&currentTrackList[currentTrackIdx]?esc(currentTrackList[currentTrackIdx].title||''):'')+'</div>';
    html += '<div class="queue-track-artist">'+(currentTrackIdx>=0&&currentTrackList[currentTrackIdx]?esc(currentTrackList[currentTrackIdx].artist||''):'')+'</div></div></div>';
    for(let i=currentTrackIdx+1;i<currentTrackList.length;i++){
      const t = currentTrackList[i];
      html += '<div class="queue-track" onclick="window._playFromRow('+i+')">';
      html += '<img class="queue-track-cover" src="'+proxyImg(t.cover)+'" alt="">';
      html += '<div class="queue-track-info"><div class="queue-track-title">'+esc(t.title||'')+'</div>';
      html += '<div class="queue-track-artist">'+esc(t.artist||'')+'</div></div></div>';
    }
  }
  if(!html) html = '<div style="text-align:center;padding:40px;color:var(--muted)">La coda è vuota</div>';
  $("#queueList").innerHTML = html;
}

async function downloadTrack(id,title){
  try{
    const r = await fetch("/api/download",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({link:id})
    });
    const d = await r.json();
    toast(d.message||"Download avviato");
  }catch(e){
    toast("Errore nel download");
  }
}

async function downloadAlbumTracks(album_id,artist,title){
  try{
    const r = await fetch("/api/download_album",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({album_id:album_id,artist_name:artist,album_title:title})
    });
    const d = await r.json();
    toast(d.message||"Download album avviato");
  }catch(e){
    toast("Errore nel download");
  }
}

async function downloadPlaylistTracks(ids){
  if(!ids||!ids.length){toast("Nessun brano da scaricare");return;}
  try{
    const r = await fetch("/api/download_batch",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({track_ids:ids})
    });
    const d = await r.json();
    toast(d.message||"Download avviato");
  }catch(e){
    toast("Errore nel download");
  }
}

function downloadCurrent(){
  if(currentTrackIdx>=0 && currentTrackList[currentTrackIdx]){
    const t = currentTrackList[currentTrackIdx];
    if(t.id) downloadTrack(t.id, t.title);
    else toast("Nessun brano in riproduzione");
  }
}

async function loadSidebarPlaylists(){
  try{
    const r = await fetch("/api/trending");
    const d = await r.json();
    let html = '';
    (d.chart_playlists||[]).slice(0,15).forEach(p=>{
      html += '<div class="playlist-item" onclick="openPlaylist(\''+p.id+'\')">'+esc(p.name)+'</div>';
    });
    $("#sidebarPlaylists").innerHTML = html;
  }catch(e){}
}

function initEqualizer(){
  // CSS handles the animation via @keyframes eqBounce
}

// Progress bar click+drag
(function(){
  const bar = $("#progressBar");
  let dragging = false;
  function seek(e){
    const rect = bar.getBoundingClientRect();
    const pct = Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width));
    if(audio.duration) audio.currentTime = pct * audio.duration;
  }
  bar.addEventListener("mousedown", e=>{
    dragging = true;
    seek(e);
  });
  document.addEventListener("mousemove", e=>{ if(dragging) seek(e); });
  document.addEventListener("mouseup", ()=>{ dragging = false; });
})();

// Volume bar click+drag
(function(){
  const bar = $("#volBar");
  let dragging = false;
  function setVol(e){
    const rect = bar.getBoundingClientRect();
    const pct = Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width));
    audio.volume = pct;
    $("#volFill").style.width = (pct*100)+"%";
    updateVolIcon(pct);
  }
  bar.addEventListener("mousedown", e=>{
    dragging = true;
    setVol(e);
  });
  document.addEventListener("mousemove", e=>{ if(dragging) setVol(e); });
  document.addEventListener("mouseup", ()=>{ dragging = false; });
})();

// Keyboard shortcuts
document.addEventListener("keydown", e=>{
  if(e.target.tagName==="INPUT") return;
  if(e.code==="Space"){
    e.preventDefault();
    togglePlay();
  } else if(e.code==="ArrowLeft"){
    e.preventDefault();
    if(audio.currentTime) audio.currentTime = Math.max(0,audio.currentTime-5);
  } else if(e.code==="ArrowRight"){
    e.preventDefault();
    if(audio.duration) audio.currentTime = Math.min(audio.duration,audio.currentTime+5);
  } else if(e.code==="ArrowUp"){
    e.preventDefault();
    audio.volume = Math.min(1,audio.volume+0.05);
    $("#volFill").style.width = (audio.volume*100)+"%";
    updateVolIcon(audio.volume);
  } else if(e.code==="ArrowDown"){
    e.preventDefault();
    audio.volume = Math.max(0,audio.volume-0.05);
    $("#volFill").style.width = (audio.volume*100)+"%";
    updateVolIcon(audio.volume);
  } else if(e.code==="KeyM"){
    e.preventDefault();
    toggleMute();
  }
});

audio.volume = 0.8;

// Expose to window
window.navTo = navTo;
window.loadChart = loadChart;
window.toast = toast;
window.fmt = fmt;
window.loading = loading;
window.playTrack = playTrack;
window.fallbackToPreview = fallbackToPreview;
window.updatePlayerUI = updatePlayerUI;
window.openCurrentArtist = openCurrentArtist;
window.setPlayIcon = setPlayIcon;
window.togglePlay = togglePlay;
window.prevTrack = prevTrack;
window.nextTrack = nextTrack;
window.toggleShuffle = toggleShuffle;
window.toggleRepeat = toggleRepeat;
window.toggleMute = toggleMute;
window.updateVolIcon = updateVolIcon;
window.updatePlayingState = updatePlayingState;
window.trackRowHtml = trackRowHtml;
window.renderTracksHtml = renderTracksHtml;
window.bindTrackRows = bindTrackRows;
window.loadHome = loadHome;
window.loadNewReleases = loadNewReleases;
window.loadMomento = loadMomento;
window.openPlaylist = openPlaylist;
window.openAlbum = openAlbum;
window.playAllFromList = playAllFromList;
window.playAllTracks = playAllTracks;
window.openArtist = openArtist;
window.doSearch = doSearch;
window.loadFiles = loadFiles;
window.loadSettings = loadSettings;
window.generateArl = generateArl;
window.toggleQueue = toggleQueue;
window.renderQueue = renderQueue;
window.downloadTrack = downloadTrack;
window.downloadAlbumTracks = downloadAlbumTracks;
window.downloadPlaylistTracks = downloadPlaylistTracks;
window.downloadCurrent = downloadCurrent;
window.loadSidebarPlaylists = loadSidebarPlaylists;
window.initEqualizer = initEqualizer;

// Init
initEqualizer();
loadHome();
loadSidebarPlaylists();

})();
</script>
</body>
</html>
'''

if __name__ == '__main__':
    print("D33Z3R in ascolto su http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
