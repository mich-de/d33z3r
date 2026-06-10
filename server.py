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

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/api/status')
def status():
    return jsonify({'arl': bool(ARL)})

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

@app.route('/api/trending')
def trending():
    try:
        charts = req.get('https://api.deezer.com/chart', timeout=10).json()
        releases = req.get('https://api.deezer.com/editorial/0/releases', timeout=10).json()
        return jsonify({
            'chart_tracks': charts.get('tracks', {}).get('data', [])[:20],
            'chart_albums': charts.get('albums', {}).get('data', [])[:18],
            'chart_playlists': charts.get('playlists', {}).get('data', [])[:12],
            'chart_podcasts': charts.get('podcasts', {}).get('data', [])[:12],
            'new_releases': releases.get('data', [])[:18]
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
        return jsonify({'playlist': pl, 'tracks': tracks.get('data', [])})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/album/<aid>')
def album_info(aid):
    try:
        al = req.get(f'https://api.deezer.com/album/{aid}', timeout=10).json()
        tracks = req.get(f'https://api.deezer.com/album/{aid}/tracks', timeout=10).json()
        return jsonify({'album': al, 'tracks': tracks.get('data', [])})
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
            'tracks': tracks.get('data', []),
            'playlists': playlists.get('data', []),
            'albums': albums.get('data', []),
            'artists': artists.get('data', [])
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/artist/<aid>')
def artist_info(aid):
    try:
        artist = req.get(f'https://api.deezer.com/artist/{aid}', timeout=10).json()
        top = req.get(f'https://api.deezer.com/artist/{aid}/top?limit=20', timeout=10).json()
        albums = req.get(f'https://api.deezer.com/artist/{aid}/albums?limit=20', timeout=10).json()
        return jsonify({'artist': artist, 'top': top.get('data', []), 'albums': albums.get('data', [])})
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
        return jsonify({'albums': data.get('data', [])[:18]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/track_info/<int:track_id>')
def track_info(track_id):
    try:
        data = req.get(f'https://api.deezer.com/track/{track_id}', timeout=10).json()
        return jsonify(data)
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
        # Forward Range header for seek support
        headers = {'User-Agent': 'Deezer/6.23.0.0'}
        range_header = request.headers.get('Range')
        if range_header:
            headers['Range'] = range_header
        r = req.get(url, timeout=30, stream=True, headers=headers)
        resp_headers = {
            'Content-Type': 'audio/mpeg',
            'Accept-Ranges': 'bytes',
            'Cache-Control': 'no-cache',
        }
        if 'Content-Length' in r.headers:
            resp_headers['Content-Length'] = r.headers['Content-Length']
        if 'Content-Range' in r.headers:
            resp_headers['Content-Range'] = r.headers['Content-Range']
        # Blowfish decryption for crypted streams
        bf_key = generateBlowfishKey(str(track_id))
        CHUNK_SIZE = 2048 * 3  # 6144 bytes per chunk
        def generate():
            for chunk in r.iter_content(CHUNK_SIZE):
                if chunk:
                    # Decrypt first 2048 bytes of each chunk
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

@app.route('/api/download', methods=['POST'])
def download():
    data = request.json
    link = data.get('link', '').strip()
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

@app.route('/api/files')
def list_files():
    files = []
    for f in os.listdir(DOWNLOAD_DIR):
        if f.endswith('.mp3'):
            files.append({'name': f, 'size': os.path.getsize(os.path.join(DOWNLOAD_DIR, f))})
    return jsonify(files)

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

HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>D33Z3R</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@500;700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#121212;--surface:#181818;--surface2:#282828;--surface3:#333;
  --accent:#1DB954;--text:#fff;--dim:#b3b3b3;--muted:#727272;
  --player-h:90px;--sidebar-w:240px;
}
html,body{height:100%;background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;font-size:14px;overflow:hidden}
a{color:inherit;text-decoration:none}
button{background:none;border:none;color:inherit;cursor:pointer;font:inherit}
input{font:inherit}
::-webkit-scrollbar{width:8px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--surface3);border-radius:4px}
::-webkit-scrollbar-thumb:hover{background:var(--muted)}

.app{display:grid;grid-template-columns:var(--sidebar-w) 1fr;grid-template-rows:1fr var(--player-h);height:100vh;overflow:hidden}

/* Sidebar */
.sidebar{grid-row:1;display:flex;flex-direction:column;background:var(--bg);border-right:1px solid var(--surface2);overflow:hidden}
.sidebar-logo{padding:24px 20px 16px;font-family:'DM Sans',sans-serif;font-weight:700;font-size:22px;letter-spacing:1px;color:var(--text)}
.sidebar-search{padding:0 16px 12px}
.sidebar-search input{width:100%;padding:8px 12px;border-radius:6px;border:none;background:var(--surface2);color:var(--text);font-size:13px;outline:none}
.sidebar-search input::placeholder{color:var(--muted)}
.sidebar-search input:focus{background:var(--surface3)}
.sidebar-nav{padding:8px 8px 16px;display:flex;flex-direction:column;gap:2px}
.nav-item{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:6px;color:var(--dim);font-size:14px;font-weight:500;transition:color .15s,background .15s}
.nav-item:hover{color:var(--text);background:var(--surface)}
.nav-item.active{color:var(--text)}
.nav-item.active::before{content:'';position:absolute;left:0;width:3px;height:20px;background:var(--accent);border-radius:0 2px 2px 0}
.nav-item{position:relative}
.nav-item svg{width:20px;height:20px;flex-shrink:0;fill:currentColor}
.sidebar-divider{height:1px;background:var(--surface2);margin:4px 16px}
.sidebar-playlists-label{padding:16px 20px 8px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;color:var(--muted)}
.sidebar-playlists{flex:1;overflow-y:auto;padding:0 8px 8px}
.playlist-item{padding:8px 12px;border-radius:6px;font-size:13px;color:var(--dim);cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:color .15s}
.playlist-item:hover{color:var(--text);background:var(--surface)}

/* Main area */
.main{grid-row:1;display:flex;flex-direction:column;overflow:hidden}
.header{height:64px;display:flex;align-items:center;justify-content:space-between;padding:0 32px;background:var(--bg);border-bottom:1px solid var(--surface2);flex-shrink:0}
.header-left{display:flex;align-items:center;gap:12px}
.header-back{width:32px;height:32px;border-radius:50%;background:var(--surface2);display:flex;align-items:center;justify-content:center;cursor:pointer;transition:background .15s}
.header-back:hover{background:var(--surface3)}
.header-back svg{width:16px;height:16px;fill:var(--text)}
.header-right{display:flex;align-items:center;gap:12px}
.header-btn{padding:8px 16px;border-radius:20px;font-size:13px;font-weight:600;transition:background .15s}
.header-btn.primary{background:var(--accent);color:#000}
.header-btn.primary:hover{background:#1ed760}
.header-btn.secondary{background:var(--surface2);color:var(--text)}
.header-btn.secondary:hover{background:var(--surface3)}

.content{flex:1;overflow-y:auto;padding:0 32px 32px}

/* Section titles */
.section-title{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;color:var(--muted);margin-bottom:16px}

/* Track rows */
.track-list{display:flex;flex-direction:column}
.track-row{display:grid;grid-template-columns:36px 1fr 200px 60px 48px;align-items:center;gap:16px;padding:8px 12px;border-radius:6px;cursor:pointer;transition:background .15s}
.track-row:hover{background:var(--surface)}
.track-row.playing{background:var(--surface2)}
.track-num{font-size:14px;color:var(--dim);text-align:center;font-variant-numeric:tabular-nums}
.track-row:hover .track-num{display:none}
.track-row:hover .track-play-icon{display:flex}
.track-play-icon{display:none;align-items:center;justify-content:center}
.track-play-icon svg{width:16px;height:16px;fill:var(--text)}
.track-info{display:flex;align-items:center;gap:12px;overflow:hidden}
.track-thumb{width:40px;height:40px;border-radius:4px;object-fit:cover;flex-shrink:0;background:var(--surface3)}
.track-text{overflow:hidden}
.track-title{font-size:14px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.track-title.playing{color:var(--accent)}
.track-artist{font-size:12px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.track-album{font-size:13px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.track-duration{font-size:13px;color:var(--dim);text-align:right;font-variant-numeric:tabular-nums}
.track-dl{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;opacity:0;transition:opacity .15s,background .15s}
.track-row:hover .track-dl{opacity:1}
.track-dl:hover{background:var(--surface2)}
.track-dl svg{width:16px;height:16px;fill:var(--dim)}

/* Cards */
.cards-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:24px;margin-bottom:40px}
.card{background:var(--surface);border-radius:8px;padding:16px;cursor:pointer;transition:background .2s,transform .2s}
.card:hover{background:var(--surface2);transform:translateY(-2px)}
.card-cover{width:100%;aspect-ratio:1;border-radius:6px;object-fit:cover;background:var(--surface3);margin-bottom:12px}
.card-title{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:4px}
.card-sub{font-size:13px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* Album header */
.album-header{display:flex;gap:32px;margin-bottom:32px}
.album-cover{width:230px;height:230px;border-radius:8px;object-fit:cover;flex-shrink:0;background:var(--surface3)}
.album-meta{display:flex;flex-direction:column;justify-content:flex-end;gap:8px}
.album-label{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:1px}
.album-title{font-family:'DM Sans',sans-serif;font-size:48px;font-weight:700;line-height:1.1}
.album-info{font-size:13px;color:var(--dim)}
.album-actions{display:flex;gap:12px;margin-top:16px}

/* Artist header */
.artist-header{display:flex;align-items:flex-end;gap:32px;margin-bottom:32px}
.artist-avatar{width:200px;height:200px;border-radius:50%;object-fit:cover;background:var(--surface3)}
.artist-name{font-family:'DM Sans',sans-serif;font-size:56px;font-weight:700;line-height:1}
.artist-stats{font-size:13px;color:var(--dim)}

/* Search sections */
.search-results .section{margin-bottom:32px}
.search-input{font-size:14px;padding:12px 16px;border-radius:8px;border:none;background:var(--surface2);color:var(--text);width:400px;outline:none}
.search-input:focus{box-shadow:0 0 0 2px var(--accent)}

/* Home grid */
.home-section{margin-bottom:40px}
.home-section-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.home-section-title h3{font-size:22px;font-weight:700;font-family:'DM Sans',sans-serif}
.home-section-title .see-all{font-size:12px;font-weight:600;color:var(--dim);text-transform:uppercase;letter-spacing:1px;cursor:pointer}
.home-section-title .see-all:hover{color:var(--text)}

/* Player bar */
.player{grid-column:2;display:flex;align-items:center;justify-content:space-between;padding:0 16px;background:var(--bg);border-top:1px solid var(--surface2);height:var(--player-h);z-index:100}
.player-track{display:flex;align-items:center;gap:12px;width:280px;min-width:180px}
.player-cover{width:56px;height:56px;border-radius:4px;object-fit:cover;background:var(--surface3);cursor:pointer}
.player-info{overflow:hidden}
.player-title{font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer}
.player-title:hover{text-decoration:underline}
.player-artist{font-size:11px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer}
.player-artist:hover{color:var(--text);text-decoration:underline}
.player-center{display:flex;flex-direction:column;align-items:center;gap:8px;flex:1;max-width:600px}
.player-controls{display:flex;align-items:center;gap:20px}
.ctrl-btn{width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:50%;transition:transform .1s}
.ctrl-btn:hover{transform:scale(1.1)}
.ctrl-btn svg{fill:var(--dim);transition:fill .15s}
.ctrl-btn:hover svg{fill:var(--text)}
.ctrl-btn.active svg{fill:var(--accent)}
.play-btn{width:36px;height:36px;border-radius:50%;background:var(--text);display:flex;align-items:center;justify-content:center}
.play-btn:hover{transform:scale(1.06)}
.play-btn svg{fill:var(--bg);width:16px;height:16px}
.progress-row{display:flex;align-items:center;gap:8px;width:100%}
.progress-time{font-size:11px;color:var(--dim);min-width:36px;text-align:center;font-variant-numeric:tabular-nums}
.progress-bar{flex:1;height:4px;background:var(--surface3);border-radius:2px;cursor:pointer;position:relative;overflow:visible}
.progress-bar:hover{height:6px}
.progress-fill{height:100%;background:var(--dim);border-radius:2px;position:relative;transition:none}
.progress-bar:hover .progress-fill{background:var(--accent)}
.progress-thumb{width:12px;height:12px;background:var(--text);border-radius:50%;position:absolute;right:-6px;top:50%;transform:translateY(-50%);opacity:0;transition:opacity .15s}
.progress-bar:hover .progress-thumb{opacity:1}
.player-right{display:flex;align-items:center;gap:12px;width:220px;justify-content:flex-end}
.vol-group{display:flex;align-items:center;gap:8px}
.vol-btn{width:32px;height:32px;display:flex;align-items:center;justify-content:center}
.vol-btn svg{fill:var(--dim);transition:fill .15s}
.vol-btn:hover svg{fill:var(--text)}
.vol-bar{width:100px;height:4px;background:var(--surface3);border-radius:2px;cursor:pointer;position:relative}
.vol-bar:hover{height:6px}
.vol-fill{height:100%;background:var(--dim);border-radius:2px;transition:none}
.vol-bar:hover .vol-fill{background:var(--text)}
.dl-btn{width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:50%;transition:background .15s}
.dl-btn:hover{background:var(--surface2)}
.dl-btn svg{fill:var(--dim);transition:fill .15s}
.dl-btn:hover svg{fill:var(--text)}

/* Queue panel */
.queue-overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:200;opacity:0;pointer-events:none;transition:opacity .25s}
.queue-overlay.open{opacity:1;pointer-events:auto}
.queue-panel{position:fixed;top:0;right:0;bottom:var(--player-h);width:360px;background:var(--surface);z-index:201;transform:translateX(100%);transition:transform .25s;overflow-y:auto;display:flex;flex-direction:column}
.queue-panel.open{transform:translateX(0)}
.queue-header{padding:16px 20px;border-bottom:1px solid var(--surface2);display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.queue-header h3{font-size:16px;font-weight:700}
.queue-close{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;transition:background .15s}
.queue-close:hover{background:var(--surface3)}
.queue-close svg{width:14px;height:14px;fill:var(--dim)}
.queue-list{flex:1;overflow-y:auto;padding:8px 12px}

/* Loading */
.loading-spinner{display:flex;align-items:center;justify-content:center;padding:60px 0}
.loading-spinner::after{content:'';width:32px;height:32px;border:3px solid var(--surface3);border-top-color:var(--accent);border-radius:50%;animation:spin .6s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

/* Toast */
.toast-container{position:fixed;bottom:calc(var(--player-h) + 16px);right:24px;z-index:300;display:flex;flex-direction:column;gap:8px}
.toast{background:var(--surface2);color:var(--text);padding:12px 20px;border-radius:8px;font-size:13px;font-weight:500;box-shadow:0 4px 16px rgba(0,0,0,.3);animation:toastIn .25s ease,toastOut .3s ease 2.7s forwards}
@keyframes toastIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes toastOut{to{opacity:0;transform:translateY(10px)}}
</style>
</head>
<body>
<div class="app">
  <!-- Sidebar -->
  <div class="sidebar">
    <div class="sidebar-logo">D33Z3R</div>
    <div class="sidebar-search">
      <input type="text" id="searchInput" placeholder="Cerca..." />
    </div>
    <nav class="sidebar-nav" id="sidebarNav">
      <a class="nav-item active" data-view="home" onclick="navTo('home')">
        <svg viewBox="0 0 24 24"><path d="M12 3L4 9v12h5v-7h6v7h5V9z"/></svg>
        Home
      </a>
      <a class="nav-item" data-view="momento" onclick="navTo('momento')">
        <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
        Del Momento
      </a>
      <a class="nav-item" data-view="search" onclick="navTo('search')">
        <svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0016 9.5 6.5 6.5 0 109.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
        Cerca
      </a>
      <a class="nav-item" data-view="library" onclick="navTo('library')">
        <svg viewBox="0 0 24 24"><path d="M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H8V4h12v12z"/></svg>
        Libreria
      </a>
      <a class="nav-item" data-view="new" onclick="navTo('new')">
        <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm5 11h-4v4h-2v-4H7v-2h4V7h2v4h4v2z"/></svg>
        Novita
      </a>
    </nav>
    <div class="sidebar-divider"></div>
    <div class="sidebar-playlists-label">Playlist</div>
    <div class="sidebar-playlists" id="sidebarPlaylists"></div>
  </div>

  <!-- Main -->
  <div class="main">
    <div class="header">
      <div class="header-left">
        <div class="header-back" id="backBtn" onclick="history.back()" style="visibility:hidden">
          <svg viewBox="0 0 24 24"><path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/></svg>
        </div>
      </div>
      <div class="header-right" id="headerRight"></div>
    </div>
    <div class="content" id="content">
      <div class="loading-spinner"></div>
    </div>
  </div>

  <!-- Player -->
  <div class="player" id="playerBar">
    <div class="player-track" id="playerTrack">
      <img class="player-cover" id="playerCover" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E" alt="" />
      <div class="player-info">
        <div class="player-title" id="playerTitle">Nessuna traccia</div>
        <div class="player-artist" id="playerArtist"></div>
      </div>
    </div>
    <div class="player-center">
      <div class="player-controls">
        <button class="ctrl-btn" id="shuffleBtn" onclick="toggleShuffle()" title="Shuffle">
          <svg width="16" height="16" viewBox="0 0 24 24"><path d="M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z"/></svg>
        </button>
        <button class="ctrl-btn" onclick="prevTrack()" title="Previous">
          <svg width="16" height="16" viewBox="0 0 24 24"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg>
        </button>
        <button class="play-btn" id="playBtn" onclick="togglePlay()" title="Play">
          <svg viewBox="0 0 24 24" id="playIcon"><path d="M8 5v14l11-7z"/></svg>
        </button>
        <button class="ctrl-btn" onclick="nextTrack()" title="Next">
          <svg width="16" height="16" viewBox="0 0 24 24"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
        </button>
        <button class="ctrl-btn" id="repeatBtn" onclick="toggleRepeat()" title="Repeat">
          <svg width="16" height="16" viewBox="0 0 24 24"><path d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z"/></svg>
        </button>
      </div>
      <div class="progress-row">
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
      <button class="ctrl-btn" id="queueBtn" onclick="toggleQueue()" title="Coda">
        <svg width="16" height="16" viewBox="0 0 24 24"><path d="M15 6H3v2h12V6zm0 4H3v2h12v-2zM3 16h8v-2H3v2zM17 6v8.18c-.31-.11-.65-.18-1-.18-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3V8h3V6h-5z"/></svg>
      </button>
      <div class="vol-group">
        <button class="vol-btn" id="volBtn" onclick="toggleMute()">
          <svg width="18" height="18" viewBox="0 0 24 24" id="volIcon"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg>
        </button>
        <div class="vol-bar" id="volBar">
          <div class="vol-fill" id="volFill" style="width:80%"></div>
        </div>
      </div>
      <button class="dl-btn" onclick="downloadCurrent()" title="Scarica">
        <svg width="16" height="16" viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
      </button>
    </div>
  </div>
</div>

<!-- Queue panel -->
<div class="queue-overlay" id="queueOverlay" onclick="toggleQueue()"></div>
<div class="queue-panel" id="queuePanel">
  <div class="queue-header">
    <h3>Coda</h3>
    <button class="queue-close" onclick="toggleQueue()">
      <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
    </button>
  </div>
  <div class="queue-list" id="queueList"></div>
</div>

<!-- Toasts -->
<div class="toast-container" id="toastContainer"></div>

<audio id="audio" preload="auto"></audio>

<script>
(function(){
"use strict";

var audio = document.getElementById("audio");
var content = document.getElementById("content");
var searchInput = document.getElementById("searchInput");
var sidebarNav = document.getElementById("sidebarNav");
var sidebarPlaylists = document.getElementById("sidebarPlaylists");
var headerRight = document.getElementById("headerRight");
var backBtn = document.getElementById("backBtn");

var state = {
  queue: [],
  queueIdx: -1,
  currentTrack: null,
  playing: false,
  shuffle: false,
  repeat: 0,
  volume: 0.8,
  muted: false,
  prevVolume: 0.8,
  history: []
};

function fmt(s) {
  if (!s && s !== 0) return "0:00";
  var m = Math.floor(s / 60);
  var sec = Math.floor(s % 60);
  return m + ":" + (sec < 10 ? "0" : "") + sec;
}

function toast(msg) {
  var t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  document.getElementById("toastContainer").appendChild(t);
  setTimeout(function() { if (t.parentNode) t.parentNode.removeChild(t); }, 3000);
}

function loading() {
  content.innerHTML = '<div class="loading-spinner"></div>';
}

function navTo(view, extra) {
  var items = sidebarNav.querySelectorAll(".nav-item");
  items.forEach(function(el) {
    el.classList.toggle("active", el.getAttribute("data-view") === view);
  });
  if (view === "home") loadHome();
  else if (view === "search") loadSearch();
  else if (view === "momento") loadMomento();
  else if (view === "new") loadNewReleases();
  else if (view === "library") loadFiles();
  else if (view === "playlist" && extra) openPlaylist(extra);
  else if (view === "album" && extra) openAlbum(extra);
  else if (view === "artist" && extra) openArtist(extra);
  else loadHome();
  content.scrollTop = 0;
  backBtn.style.visibility = state.history.length > 0 ? "visible" : "hidden";
}

function pushHistory(fn) {
  state.history.push(fn);
  backBtn.style.visibility = "visible";
}

function goBack() {
  if (state.history.length > 0) {
    state.history.pop()();
    backBtn.style.visibility = state.history.length > 0 ? "visible" : "hidden";
  }
}

backBtn.addEventListener("click", function() {
  goBack();
});

function api(url, opts) {
  return fetch(url, opts).then(function(r) { return r.json(); });
}

function trackCover(t) {
  if (t && t.album && t.album.cover && t.album.cover.medium) return t.album.cover.medium;
  if (t && t.cover) return t.cover;
  if (t && t.album_cover) return t.album_cover;
  return "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E";
}

function albumCover(a) {
  if (a && a.cover && a.cover.medium) return a.cover.medium;
  if (a && a.cover) return a.cover;
  return "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E";
}

function artistImg(a) {
  if (a && a.image) return a.image;
  if (a && a.cover) return a.cover;
  return "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E";
}

function dlSvg() {
  return '<svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>';
}

function playSvg() {
  return '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>';
}

function updatePlayerUI(t) {
  if (!t) return;
  document.getElementById("playerCover").src = trackCover(t);
  document.getElementById("playerTitle").textContent = t.title || "Sconosciuto";
  document.getElementById("playerArtist").textContent = (t.artist && t.artist.name) || t.artist_name || "";
}

function setPlayIcon(playing) {
  var icon = document.getElementById("playIcon");
  icon.innerHTML = playing
    ? '<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>'
    : '<path d="M8 5v14l11-7z"/>';
}

function updatePlayingState() {
  document.querySelectorAll(".track-row").forEach(function(row) {
    var t = state.queue[state.queueIdx];
    var id = row.getAttribute("data-id");
    var isActive = t && String(t.id) === id;
    row.classList.toggle("playing", isActive);
    var titleEl = row.querySelector(".track-title");
    if (titleEl) titleEl.classList.toggle("playing", isActive);
  });
}

function trackRowHtml(t, i, tracks) {
  var isPlaying = state.currentTrack && String(state.currentTrack.id) === String(t.id);
  var img = trackCover(t);
  var artistName = (t.artist && t.artist.name) || t.artist_name || "";
  var albumName = (t.album && t.album.title) || t.album_title || "";
  var duration = t.duration ? fmt(t.duration) : "";
  var id = t.id || "";
  return '<div class="track-row' + (isPlaying ? ' playing' : '') + '" data-id="' + id + '" data-idx="' + i + '">' +
    '<div class="track-num">' + (i + 1) + '</div>' +
    '<div class="track-play-icon">' + playSvg() + '</div>' +
    '<div class="track-info">' +
      '<img class="track-thumb" src="' + img + '" alt="" loading="lazy" />' +
      '<div class="track-text">' +
        '<div class="track-title' + (isPlaying ? ' playing' : '') + '">' + (t.title || "Sconosciuto") + '</div>' +
        '<div class="track-artist">' + artistName + '</div>' +
      '</div>' +
    '</div>' +
    '<div class="track-album">' + albumName + '</div>' +
    '<div class="track-duration">' + duration + '</div>' +
    '<button class="track-dl" data-id="' + id + '" data-title="' + (t.title || "") + '">' + dlSvg() + '</button>' +
  '</div>';
}

function renderTracksHtml(tracks, title) {
  if (!tracks || tracks.length === 0) return '<p style="color:var(--dim);padding:20px 0">Nessuna traccia trovata.</p>';
  var h = '<div class="track-list">';
  tracks.forEach(function(t, i) { h += trackRowHtml(t, i, tracks); });
  h += '</div>';
  return h;
}

function bindTrackRows(tracks) {
  content.querySelectorAll(".track-row").forEach(function(row) {
    row.addEventListener("click", function(e) {
      if (e.target.closest(".track-dl")) return;
      var idx = parseInt(row.getAttribute("data-idx"), 10);
      playTrack(tracks[idx], tracks, idx);
    });
  });
  content.querySelectorAll(".track-dl").forEach(function(btn) {
    btn.addEventListener("click", function(e) {
      e.stopPropagation();
      var id = btn.getAttribute("data-id");
      var title = btn.getAttribute("data-title");
      downloadTrack(id, title);
    });
  });
}

function playTrack(track, list, idx) {
  if (!track) return;
  state.queue = list || [track];
  state.queueIdx = idx !== undefined ? idx : 0;
  state.currentTrack = track;
  updatePlayerUI(track);
  loadStream(track);
}

function loadStream(track) {
  if (!track || !track.id) return;
  audio.src = "/api/stream_track/" + track.id;
  audio.load();
  audio.play().catch(function() {
    fallbackToPreview(track);
  });
}

function fallbackToPreview(t) {
  if (!t || !t.id) return;
  audio.src = "/api/stream_preview/" + t.id;
  audio.load();
  audio.play().catch(function() {
    toast("Impossibile riprodurre: " + (t.title || ""));
  });
}

audio.onplay = function() {
  state.playing = true;
  setPlayIcon(true);
  updatePlayingState();
};

audio.onpause = function() {
  state.playing = false;
  setPlayIcon(false);
};

audio.onended = function() {
  if (state.repeat === 2) {
    audio.currentTime = 0;
    audio.play();
  } else {
    nextTrack();
  }
};

audio.ontimeupdate = function() {
  if (audio.duration) {
    var pct = (audio.currentTime / audio.duration) * 100;
    document.getElementById("progressFill").style.width = pct + "%";
    document.getElementById("currentTime").textContent = fmt(audio.currentTime);
    document.getElementById("totalTime").textContent = fmt(audio.duration);
  }
};

function togglePlay() {
  if (!audio.src) return;
  if (state.playing) audio.pause();
  else audio.play();
}

function nextTrack() {
  if (state.queue.length === 0) return;
  if (state.shuffle) {
    state.queueIdx = Math.floor(Math.random() * state.queue.length);
  } else {
    state.queueIdx = (state.queueIdx + 1) % state.queue.length;
  }
  var t = state.queue[state.queueIdx];
  if (t) {
    state.currentTrack = t;
    updatePlayerUI(t);
    loadStream(t);
  }
}

function prevTrack() {
  if (state.queue.length === 0) return;
  if (audio.currentTime > 3) {
    audio.currentTime = 0;
    return;
  }
  state.queueIdx = (state.queueIdx - 1 + state.queue.length) % state.queue.length;
  var t = state.queue[state.queueIdx];
  if (t) {
    state.currentTrack = t;
    updatePlayerUI(t);
    loadStream(t);
  }
}

function toggleShuffle() {
  state.shuffle = !state.shuffle;
  document.getElementById("shuffleBtn").classList.toggle("active", state.shuffle);
  toast(state.shuffle ? "Shuffle attivato" : "Shuffle disattivato");
}

function toggleRepeat() {
  state.repeat = (state.repeat + 1) % 3;
  var btn = document.getElementById("repeatBtn");
  btn.classList.toggle("active", state.repeat > 0);
  var labels = ["Repeat disattivato", "Ripeti tutto", "Ripeti traccia"];
  toast(labels[state.repeat]);
}

function toggleMute() {
  if (state.muted) {
    state.muted = false;
    audio.volume = state.prevVolume;
    state.volume = state.prevVolume;
  } else {
    state.muted = true;
    state.prevVolume = state.volume;
    audio.volume = 0;
    state.volume = 0;
  }
  updateVolIcon(state.volume);
  document.getElementById("volFill").style.width = (state.volume * 100) + "%";
}

function updateVolIcon(v) {
  var icon = document.getElementById("volIcon");
  if (v === 0) {
    icon.innerHTML = '<path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/>';
  } else if (v < 0.5) {
    icon.innerHTML = '<path d="M18.5 12c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM5 9v6h4l5 5V4L9 9H5z"/>';
  } else {
    icon.innerHTML = '<path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>';
  }
}

function updateVolBar(e) {
  var bar = document.getElementById("volBar");
  var rect = bar.getBoundingClientRect();
  var pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  state.volume = pct;
  state.muted = pct === 0;
  audio.volume = pct;
  document.getElementById("volFill").style.width = (pct * 100) + "%";
  updateVolIcon(pct);
}

document.getElementById("volBar").addEventListener("click", updateVolBar);
(function() {
  var dragging = false;
  var bar = document.getElementById("volBar");
  bar.addEventListener("mousedown", function(e) {
    dragging = true;
    updateVolBar(e);
  });
  document.addEventListener("mousemove", function(e) {
    if (dragging) updateVolBar(e);
  });
  document.addEventListener("mouseup", function() { dragging = false; });
})();

document.getElementById("progressBar").addEventListener("click", function(e) {
  if (!audio.duration) return;
  var rect = this.getBoundingClientRect();
  var pct = (e.clientX - rect.left) / rect.width;
  audio.currentTime = pct * audio.duration;
});

function toggleQueue() {
  document.getElementById("queueOverlay").classList.toggle("open");
  document.getElementById("queuePanel").classList.toggle("open");
  if (document.getElementById("queuePanel").classList.contains("open")) renderQueue();
}

function renderQueue() {
  var list = document.getElementById("queueList");
  if (state.queue.length === 0) {
    list.innerHTML = '<p style="color:var(--dim);padding:20px;text-align:center">La coda e\' vuota</p>';
    return;
  }
  var h = "";
  state.queue.forEach(function(t, i) {
    var isCurrent = i === state.queueIdx;
    var artistName = (t.artist && t.artist.name) || t.artist_name || "";
    h += '<div class="track-row' + (isCurrent ? ' playing' : '') + '" data-qidx="' + i + '">' +
      '<div class="track-num">' + (isCurrent ? '&#9654;' : (i + 1)) + '</div>' +
      '<div class="track-info">' +
        '<img class="track-thumb" src="' + trackCover(t) + '" alt="" loading="lazy" />' +
        '<div class="track-text">' +
          '<div class="track-title' + (isCurrent ? ' playing' : '') + '">' + (t.title || "Sconosciuto") + '</div>' +
          '<div class="track-artist">' + artistName + '</div>' +
        '</div>' +
      '</div>' +
      '<div class="track-duration">' + (t.duration ? fmt(t.duration) : '') + '</div>' +
    '</div>';
  });
  list.innerHTML = h;
  list.querySelectorAll(".track-row").forEach(function(row) {
    row.addEventListener("click", function() {
      var idx = parseInt(row.getAttribute("data-qidx"), 10);
      state.queueIdx = idx;
      state.currentTrack = state.queue[idx];
      updatePlayerUI(state.currentTrack);
      loadStream(state.currentTrack);
      renderQueue();
    });
  });
}

function openCurrentArtist() {
  if (state.currentTrack && state.currentTrack.artist && state.currentTrack.artist.id) {
    openArtist(state.currentTrack.artist.id);
  }
}

document.getElementById("playerTitle").addEventListener("click", openCurrentArtist);
document.getElementById("playerArtist").addEventListener("click", openCurrentArtist);

function loadHome() {
  loading();
  state.history = [];
  backBtn.style.visibility = "hidden";
  headerRight.innerHTML = "";
  api("/api/trending").then(function(data) {
    var h = "";
    if (data.chart_playlists && data.chart_playlists.length) {
      h += '<div class="home-section"><div class="home-section-title"><h3>Playlist del momento</h3></div><div class="cards-grid">';
      data.chart_playlists.slice(0, 6).forEach(function(p) {
        h += '<div class="card" onclick="navTo(\'playlist\',' + p.id + ')">' +
          '<img class="card-cover" src="' + (p.image || p.cover || "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E") + '" alt="" loading="lazy" />' +
          '<div class="card-title">' + (p.name || p.title || "") + '</div>' +
          '<div class="card-sub">' + (p.description || "") + '</div>' +
        '</div>';
      });
      h += '</div></div>';
    }
    if (data.chart_albums && data.chart_albums.length) {
      h += '<div class="home-section"><div class="home-section-title"><h3>Album del momento</h3></div><div class="cards-grid">';
      data.chart_albums.slice(0, 6).forEach(function(a) {
        h += '<div class="card" onclick="navTo(\'album\',' + a.id + ')">' +
          '<img class="card-cover" src="' + albumCover(a) + '" alt="" loading="lazy" />' +
          '<div class="card-title">' + (a.title || "") + '</div>' +
          '<div class="card-sub">' + (a.artist && a.artist.name || "") + '</div>' +
        '</div>';
      });
      h += '</div></div>';
    }
    if (data.chart_tracks && data.chart_tracks.length) {
      h += '<div class="home-section"><div class="home-section-title"><h3>Classifica</h3></div>';
      h += renderTracksHtml(data.chart_tracks, "Classifica");
      h += '</div>';
    }
    if (data.new_releases && data.new_releases.length) {
      h += '<div class="home-section"><div class="home-section-title"><h3>Novita</h3></div><div class="cards-grid">';
      data.new_releases.slice(0, 6).forEach(function(a) {
        h += '<div class="card" onclick="navTo(\'album\',' + a.id + ')">' +
          '<img class="card-cover" src="' + albumCover(a) + '" alt="" loading="lazy" />' +
          '<div class="card-title">' + (a.title || "") + '</div>' +
          '<div class="card-sub">' + (a.artist && a.artist.name || "") + '</div>' +
        '</div>';
      });
      h += '</div></div>';
    }
    content.innerHTML = h || '<p style="color:var(--dim);padding:40px 0">Nessun contenuto disponibile.</p>';
    if (data.chart_tracks) bindTrackRows(data.chart_tracks);
  }).catch(function() {
    content.innerHTML = '<p style="color:var(--dim);padding:40px 0">Errore nel caricamento.</p>';
  });
}

function loadSearch() {
  state.history = [];
  backBtn.style.visibility = "hidden";
  headerRight.innerHTML = '<input type="text" class="search-input" id="mainSearchInput" placeholder="Cerca brani, album, artisti..." />';
  var ms = document.getElementById("mainSearchInput");
  ms.focus();
  ms.addEventListener("keydown", function(e) {
    if (e.key === "Enter") doSearch(ms.value);
  });
  if (searchInput.value) doSearch(searchInput.value);
}

function loadNewReleases() {
  loading();
  pushHistory(function() { navTo("home"); });
  headerRight.innerHTML = "";
  api("/api/new_releases").then(function(data) {
    var albums = data.albums || [];
    if (albums.length === 0) {
      content.innerHTML = '<p style="color:var(--dim);padding:40px 0">Nessuna novita disponibile.</p>';
      return;
    }
    var h = '<div class="cards-grid">';
    albums.forEach(function(a) {
      h += '<div class="card" onclick="navTo(\'album\',' + a.id + ')">' +
        '<img class="card-cover" src="' + albumCover(a) + '" alt="" loading="lazy" />' +
        '<div class="card-title">' + (a.title || "") + '</div>' +
        '<div class="card-sub">' + (a.artist && a.artist.name || "") + '</div>' +
      '</div>';
    });
    h += '</div>';
    content.innerHTML = h;
  }).catch(function() {
    content.innerHTML = '<p style="color:var(--dim);padding:40px 0">Errore nel caricamento.</p>';
  });
}

function loadMomento() {
  loading();
  pushHistory(function() { navTo("home"); });
  headerRight.innerHTML = "";
  api("/api/trending").then(function(data) {
    var tracks = data.chart_tracks || [];
    if (tracks.length === 0) {
      content.innerHTML = '<p style="color:var(--dim);padding:40px 0">Nessuna traccia del momento.</p>';
      return;
    }
    var h = '<div class="section-title" style="margin-bottom:16px">Top del momento</div>';
    h += renderTracksHtml(tracks, "Top del momento");
    content.innerHTML = h;
    bindTrackRows(tracks);
  }).catch(function() {
    content.innerHTML = '<p style="color:var(--dim);padding:40px 0">Errore nel caricamento.</p>';
  });
}

function openPlaylist(id) {
  loading();
  pushHistory(function() { navTo("home"); });
  headerRight.innerHTML = "";
  api("/api/playlist/" + id).then(function(data) {
    var pl = data.playlist || {};
    var tracks = data.tracks || [];
    var h = '<div class="album-header">' +
      '<img class="album-cover" src="' + (pl.image || pl.cover || "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E") + '" alt="" />' +
      '<div class="album-meta">' +
        '<div class="album-label">Playlist</div>' +
        '<div class="album-title">' + (pl.name || pl.title || "") + '</div>' +
        '<div class="album-info">' + (pl.description || "") + (tracks.length ? " &middot; " + tracks.length + " brani" : "") + '</div>' +
        '<div class="album-actions">' +
          '<button class="header-btn primary" onclick="playAllFromList()">Riproduci tutto</button>' +
          '<button class="header-btn secondary" onclick="downloadPlaylistTracks(getCurrentTrackIds())">Scarica tutto</button>' +
        '</div>' +
      '</div></div>';
    h += renderTracksHtml(tracks, pl.name || pl.title || "Playlist");
    content.innerHTML = h;
    bindTrackRows(tracks);
    window.getCurrentTrackIds = function() { return tracks.map(function(t) { return t.id; }).filter(Boolean); };
  }).catch(function() {
    content.innerHTML = '<p style="color:var(--dim);padding:40px 0">Playlist non trovata.</p>';
  });
}

function openAlbum(id) {
  loading();
  pushHistory(function() { navTo("home"); });
  headerRight.innerHTML = "";
  api("/api/album/" + id).then(function(data) {
    var album = data.album || {};
    var tracks = data.tracks || [];
    var artistName = (album.artist && album.artist.name) || "";
    var h = '<div class="album-header">' +
      '<img class="album-cover" src="' + albumCover(album) + '" alt="" />' +
      '<div class="album-meta">' +
        '<div class="album-label">Album</div>' +
        '<div class="album-title">' + (album.title || "") + '</div>' +
        '<div class="album-info">' + artistName + (album.year ? " &middot; " + album.year : "") + (tracks.length ? " &middot; " + tracks.length + " brani" : "") + '</div>' +
        '<div class="album-actions">' +
          '<button class="header-btn primary" onclick="playAllFromList()">Riproduci tutto</button>' +
          '<button class="header-btn secondary" onclick="downloadPlaylistTracks(getCurrentTrackIds())">Scarica tutto</button>' +
        '</div>' +
      '</div></div>';
    h += renderTracksHtml(tracks, album.title || "Album");
    content.innerHTML = h;
    bindTrackRows(tracks);
    window.getCurrentTrackIds = function() { return tracks.map(function(t) { return t.id; }).filter(Boolean); };
  }).catch(function() {
    content.innerHTML = '<p style="color:var(--dim);padding:40px 0">Album non trovato.</p>';
  });
}

function openArtist(id) {
  loading();
  pushHistory(function() { navTo("home"); });
  headerRight.innerHTML = "";
  api("/api/artist/" + id).then(function(data) {
    var artist = data.artist || {};
    var top = data.top || [];
    var albums = data.albums || [];
    var h = '<div class="artist-header">' +
      '<img class="artist-avatar" src="' + artistImg(artist) + '" alt="" />' +
      '<div class="album-meta">' +
        '<div class="album-label">Artista</div>' +
        '<div class="artist-name">' + (artist.name || "") + '</div>' +
        (artist.followers ? '<div class="artist-stats">' + artist.followers.toLocaleString() + ' follower</div>' : '') +
      '</div></div>';
    if (top.length) {
      h += '<div class="home-section"><div class="home-section-title"><h3>Top brani</h3></div>';
      h += renderTracksHtml(top, "Top brani");
      h += '</div>';
    }
    if (albums.length) {
      h += '<div class="home-section"><div class="home-section-title"><h3>Album</h3></div><div class="cards-grid">';
      albums.forEach(function(a) {
        h += '<div class="card" onclick="navTo(\'album\',' + a.id + ')">' +
          '<img class="card-cover" src="' + albumCover(a) + '" alt="" loading="lazy" />' +
          '<div class="card-title">' + (a.title || "") + '</div>' +
          '<div class="card-sub">' + (a.year || "") + '</div>' +
        '</div>';
      });
      h += '</div></div>';
    }
    content.innerHTML = h;
    bindTrackRows(top);
  }).catch(function() {
    content.innerHTML = '<p style="color:var(--dim);padding:40px 0">Artista non trovato.</p>';
  });
}

function playAllFromList() {
  var rows = content.querySelectorAll(".track-row");
  if (rows.length === 0) return;
  rows[0].click();
}

function playAllTracks() { playAllFromList(); }

function doSearch(q) {
  if (!q || !q.trim()) return;
  loading();
  searchInput.value = q;
  headerRight.innerHTML = '<input type="text" class="search-input" id="mainSearchInput" placeholder="Cerca brani, album, artisti..." value="' + q.replace(/"/g, '&quot;') + '" />';
  var ms = document.getElementById("mainSearchInput");
  ms.addEventListener("keydown", function(e) {
    if (e.key === "Enter") doSearch(ms.value);
  });
  api("/api/search?q=" + encodeURIComponent(q)).then(function(data) {
    var h = '<div class="search-results">';
    if (data.tracks && data.tracks.length) {
      h += '<div class="section"><div class="section-title" style="margin-bottom:12px">Brani</div>';
      h += renderTracksHtml(data.tracks, q);
      h += '</div>';
    }
    if (data.artists && data.artists.length) {
      h += '<div class="section"><div class="section-title" style="margin-bottom:12px">Artisti</div><div class="cards-grid">';
      data.artists.slice(0, 6).forEach(function(a) {
        h += '<div class="card" onclick="navTo(\'artist\',' + a.id + ')">' +
          '<img class="card-cover" src="' + artistImg(a) + '" alt="" loading="lazy" style="border-radius:50%" />' +
          '<div class="card-title">' + (a.name || "") + '</div>' +
          '<div class="card-sub">Artista</div>' +
        '</div>';
      });
      h += '</div></div>';
    }
    if (data.albums && data.albums.length) {
      h += '<div class="section"><div class="section-title" style="margin-bottom:12px">Album</div><div class="cards-grid">';
      data.albums.slice(0, 6).forEach(function(a) {
        h += '<div class="card" onclick="navTo(\'album\',' + a.id + ')">' +
          '<img class="card-cover" src="' + albumCover(a) + '" alt="" loading="lazy" />' +
          '<div class="card-title">' + (a.title || "") + '</div>' +
          '<div class="card-sub">' + (a.artist && a.artist.name || "") + '</div>' +
        '</div>';
      });
      h += '</div></div>';
    }
    if (data.playlists && data.playlists.length) {
      h += '<div class="section"><div class="section-title" style="margin-bottom:12px">Playlist</div><div class="cards-grid">';
      data.playlists.slice(0, 6).forEach(function(p) {
        h += '<div class="card" onclick="navTo(\'playlist\',' + p.id + ')">' +
          '<img class="card-cover" src="' + (p.image || p.cover || "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E") + '" alt="" loading="lazy" />' +
          '<div class="card-title">' + (p.name || p.title || "") + '</div>' +
        '</div>';
      });
      h += '</div></div>';
    }
    h += '</div>';
    content.innerHTML = h;
    if (data.tracks) bindTrackRows(data.tracks);
    if (!data.tracks && !data.artists && !data.albums && !data.playlists) {
      content.innerHTML = '<p style="color:var(--dim);padding:40px 0">Nessun risultato per "' + q + '"</p>';
    }
  }).catch(function() {
    content.innerHTML = '<p style="color:var(--dim);padding:40px 0">Errore nella ricerca.</p>';
  });
}

function loadFiles() {
  loading();
  pushHistory(function() { navTo("home"); });
  headerRight.innerHTML = "";
  api("/api/files").then(function(data) {
    var files = data || [];
    if (files.length === 0) {
      content.innerHTML = '<p style="color:var(--dim);padding:40px 0">Nessun file locale trovato.</p>';
      return;
    }
    var h = '<div class="section-title" style="margin-bottom:16px">File locali</div>';
    h += '<div class="track-list">';
    files.forEach(function(f, i) {
      h += '<div class="track-row" data-file="' + f.name + '">' +
        '<div class="track-num">' + (i + 1) + '</div>' +
        '<div class="track-info">' +
          '<div class="track-text">' +
            '<div class="track-title">' + f.name + '</div>' +
            '<div class="track-artist">' + (f.size || "") + '</div>' +
          '</div>' +
        '</div>' +
        '<div class="track-album"></div>' +
        '<div class="track-duration"></div>' +
        '<div class="track-dl"></div>' +
      '</div>';
    });
    h += '</div>';
    content.innerHTML = h;
    content.querySelectorAll(".track-row[data-file]").forEach(function(row) {
      row.addEventListener("click", function() {
        playLocalFile(row.getAttribute("data-file"));
      });
    });
  }).catch(function() {
    content.innerHTML = '<p style="color:var(--dim);padding:40px 0">Errore nel caricamento file.</p>';
  });
}

function playLocalFile(name) {
  if (!name) return;
  state.queue = [{id: "_local_" + name, title: name, artist: {name: "File locale"}}];
  state.queueIdx = 0;
  state.currentTrack = state.queue[0];
  updatePlayerUI(state.currentTrack);
  audio.src = "/api/stream/" + encodeURIComponent(name);
  audio.load();
  audio.play().catch(function() {
    toast("Impossibile riprodurre " + name);
  });
}

function downloadTrack(id, title) {
  toast("Download in corso: " + (title || id));
  fetch("/api/download", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({link: id})
  }).then(function(r) { return r.blob(); }).then(function(blob) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = (title || id) + ".mp3";
    a.click();
    URL.revokeObjectURL(url);
    toast("Download completato: " + (title || id));
  }).catch(function() {
    toast("Errore nel download");
  });
}

function downloadPlaylistTracks(ids) {
  if (!ids || ids.length === 0) return;
  toast("Download batch di " + ids.length + " tracce...");
  fetch("/api/download_batch", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({track_ids: ids})
  }).then(function(r) { return r.blob(); }).then(function(blob) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "playlist.zip";
    a.click();
    URL.revokeObjectURL(url);
    toast("Download completato!");
  }).catch(function() {
    toast("Errore nel download batch");
  });
}

function downloadCurrent() {
  if (state.currentTrack) {
    downloadTrack(state.currentTrack.id, state.currentTrack.title);
  } else {
    toast("Nessuna traccia in riproduzione");
  }
}

function loadSidebarPlaylists() {
  api("/api/trending").then(function(data) {
    var playlists = data.chart_playlists || [];
    var h = "";
    playlists.forEach(function(p) {
      h += '<div class="playlist-item" onclick="navTo(\'playlist\',' + p.id + ')">' + (p.name || p.title || "Playlist") + '</div>';
    });
    sidebarPlaylists.innerHTML = h;
  }).catch(function() {
    sidebarPlaylists.innerHTML = "";
  });
}

searchInput.addEventListener("keydown", function(e) {
  if (e.key === "Enter" && searchInput.value.trim()) {
    navTo("search");
    doSearch(searchInput.value);
  }
});

audio.volume = state.volume;

navTo("home");
loadSidebarPlaylists();

window.navTo = navTo;
window.loadSearch = loadSearch;
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
window.playLocalFile = playLocalFile;
window.toggleQueue = toggleQueue;
window.renderQueue = renderQueue;
window.downloadTrack = downloadTrack;
window.downloadPlaylistTracks = downloadPlaylistTracks;
window.downloadCurrent = downloadCurrent;
window.loadSidebarPlaylists = loadSidebarPlaylists;

})();
</script>
</body>
</html>'''

if __name__ == '__main__':
    print("D33Z3R in ascolto su http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
