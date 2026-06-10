# D33Z3R 🎧

An elegant, full-featured music streaming, searching, and downloading platform powered by Flask, Playwright, and Deemix.

D33Z3R provides a sleek, modern, dark-mode web application (reminiscent of premium streaming platforms) to browse, search, stream, queue, and download music directly from Deezer.

## Features

- **Beautiful Web UI**: Modern, responsive dashboard with a Spotify-like user experience.
- **On-the-fly Decryption**: Proxies and decrypts (Blowfish) high-quality audio streams in real-time.
- **Account Automation**: Playwright script to automatically register new Deezer accounts and extract authentication tokens (`ARL`).
- **Interactive CLI**: Command-line interface for direct downloading.
- **Local Library**: Integrated browser for downloaded tracks with local play support.
- **Advanced Navigation**: Browse global charts, new releases, genres, radios, and search artist catalogs.

---

## Getting Started

### 1. Prerequisites

Make sure you have Python 3 and Node.js installed on your system.

### 2. Installation

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/mich-de/d33z3r.git
   cd d33z3r
   ```

2. **Set up Python Virtual Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
   *Note: Ensure you have `flask`, `requests`, `deemix`, and `deezer-py` installed.*

3. **Install Playwright & Node dependencies** (for account creation):
   ```bash
   npm install playwright
   npx playwright install chromium
   ```

### 3. Generate Credentials & Login

Automate account creation to fetch a fresh `ARL` token:
```bash
node register-final.js
```
This writes the credentials and the `arl` token. Move the token details to `arl.txt` in the root directory:
```text
email: your-email@outlook.com
password: your-password
arl: your-decrypted-arl-token
```

---

## Usage

### Run the Web UI
Start the Flask web server:
```bash
python server.py
```
Open [http://localhost:5000](http://localhost:5000) in your web browser.

### Run the CLI Downloader
Download tracks, albums, or playlists directly in the terminal:
```bash
python download.py
```

---

## Project Structure

```text
├── register-final.js   # Automated Playwright script for Deezer account registration
├── server.py            # Flask server hosting the web application and API endpoints
├── download.py          # Interactive command-line downloader script
├── arl.txt              # Active authentication credentials (git-ignored)
├── music/               # Directory for downloaded music (git-ignored)
└── .gitignore           # File to ignore secrets, virtual environments, and downloaded files
```

---

## Disclaimer

This project is intended for educational and personal research purposes only. Please respect the terms of service of the streaming provider.
