import sys
import os
from deemix.settings import DEFAULTS
from deemix import generateDownloadObject
from deemix.downloader import Downloader
from deezer import Deezer

def load_arl():
    arl_path = os.path.join(os.path.dirname(__file__), 'arl.txt')
    with open(arl_path) as f:
        for line in f:
            if line.startswith('arl:'):
                return line.split('arl:', 1)[1].strip()
    print("ARL non trovata")
    sys.exit(1)

def main():
    arl = load_arl()
    print(f"ARL: {arl[:20]}...")

    dz = Deezer()
    dz.login_via_arl(arl)
    if not dz.logged_in:
        print("Login fallito!")
        sys.exit(1)
    print("Login riuscito!")

    settings = DEFAULTS.copy()
    settings['downloadLocation'] = os.path.join(os.path.dirname(__file__), 'music')
    os.makedirs(settings['downloadLocation'], exist_ok=True)

    link = input("\nIncolla link Deezer (track/album/playlist): ").strip()
    if not link:
        sys.exit(1)

    downloadObject = generateDownloadObject(dz, link, settings)
    downloadObject.bitrate = 1  # 1=MP3_128, 3=MP3_320, 9=FLAC

    print(f"Download: {downloadObject.title} - {downloadObject.artist}")

    dl = Downloader(dz, downloadObject, settings)
    dl.start()
    print("\nDownload completato!")

if __name__ == '__main__':
    main()
