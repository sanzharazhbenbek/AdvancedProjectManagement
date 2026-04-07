# EventSphere

EventSphere is a web app for publishing events, booking tickets, and checking people in at the door.

## Install and run

Replace `/path/to/APM_FInal` and `C:\path\to\APM_FInal` with your own local project path.

### macOS / Linux

```bash
cd /path/to/APM_FInal
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8000`.

### Windows PowerShell

```powershell
cd C:\path\to\APM_FInal
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

### Windows cmd

```cmd
cd C:\path\to\APM_FInal
py -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
python app.py
```

## Tech stack

- Python
- FastAPI
- SQLAlchemy
- Jinja2
- SQLite
