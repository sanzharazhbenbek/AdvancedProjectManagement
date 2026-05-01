# EventSphere

EventSphere is an event and ticketing management platform for browsing events, booking tickets, validating entry with QR codes, and reviewing sales or attendance reports.

## Streamlit MVP

The project now includes a Streamlit version for free deployment. This keeps the same MVP idea from the project topic:

- event creation and management
- online ticket booking
- QR-based ticket validation
- basic sales and attendance reports

### Run locally

Replace `/path/to/AdvancedProjectManagement` and `C:\path\to\AdvancedProjectManagement` with your own local project path.

#### macOS / Linux

```bash
cd /path/to/AdvancedProjectManagement
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

#### Windows PowerShell

```powershell
cd C:\path\to\AdvancedProjectManagement
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run streamlit_app.py
```

#### Windows cmd

```cmd
cd C:\path\to\AdvancedProjectManagement
py -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Open the local URL printed by Streamlit, usually `http://localhost:8501`.

Seed accounts created on first run:

- Admin: `admin@eventsphere.local` / `Admin123!`
- Organizer: `organizer@eventsphere.local` / `Organizer123!`
- User: `user@eventsphere.local` / `User123!`

### Free deployment

1. Push the repository to GitHub.
2. Open [Streamlit Community Cloud](https://share.streamlit.io/).
3. Create a new app and choose `streamlit_app.py` as the entry file.
4. Deploy without renting a separate server.

Note: the Streamlit deployment is a good MVP/demo option. It still uses SQLite, so it is best for presentation, testing, and small-scale use rather than production traffic.

## Legacy FastAPI version

The original FastAPI app is still in the repository. If you need it for comparison or teacher discussion, you can still run:

```bash
python app.py
```

Then open `http://127.0.0.1:8000`.

## Tech stack

- Python
- Streamlit
- SQLAlchemy
- SQLite
- FastAPI and Jinja2 version retained in the repository
