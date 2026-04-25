# PDF Translator Pro (Full-Stack Web App)

A complete web-based diploma project for translating PDF content into selected languages, with a Flask backend API and a modern animated frontend.

## Highlights

- Full-stack architecture: Flask backend + HTML/CSS/JavaScript frontend.
- No Streamlit.
- Native-language ready PDF output with Unicode font mapping for Hindi, Marathi, Tamil, Telugu, Kannada, Malayalam, Gujarati, Bengali, Punjabi and more.
- Dual translation engines:
  - Primary: googletrans
  - Backup: deep-translator
- Background translation jobs with live polling progress.
- Interactive UI: animated, colorful, responsive, presentation-ready.

## Project Structure

- app.py: Flask backend, translation logic, API endpoints
- templates/index.html: frontend page
- static/css/style.css: styling and animations
- static/js/app.js: frontend interactions and API integration
- fonts/: downloaded Unicode fonts used for generated PDFs
- requirements.txt: Python dependencies

## API Endpoints

- GET /: main web app
- POST /api/jobs: create translation job (PDF upload)
- GET /api/jobs/<job_id>: poll job status and stats
- GET /api/jobs/<job_id>/download: download translated PDF
- POST /api/sample-translate: quick text translation demo
- GET /api/languages: language and font matrix

## Run Steps (Windows)

1. Open terminal in project folder:

~~~powershell
cd "c:\Users\Lenovo\OneDrive\Desktop\projects(not complited\PDFTranslator_Final_Full"
~~~

2. Create virtual environment (if needed):

~~~powershell
python -m venv venv
~~~

3. Activate virtual environment:

~~~powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& ".\venv\Scripts\Activate.ps1"
~~~

4. Install dependencies:

~~~powershell
python -m pip install --upgrade pip
python -m pip install -r .\requirements.txt
~~~

5. Run backend server:

~~~powershell
python .\app.py
~~~

6. Open browser:

- http://127.0.0.1:5000

## Demo Flow

1. Upload a text-based PDF.
2. Select target language.
3. Keep backup engine enabled for strongest reliability.
4. Set chunk size if needed.
5. Click Start Translation.
6. Watch live progress and stats.
7. Download translated PDF.

## Notes

- Internet is required for translation services and first-time font downloads.
- Image-only scanned PDFs must be OCR-processed first.
- If one engine fails for a chunk, backup engine is used. If both fail, original chunk is kept.

## Troubleshooting

- If dependency install fails, run with venv python explicitly:

~~~powershell
.\venv\Scripts\python.exe -m pip install -r .\requirements.txt
~~~

- If app does not start, verify Flask is installed:

~~~powershell
python -m pip show Flask
~~~

- If port 5000 is busy, run:

~~~powershell
python .\app.py --port 5001
~~~
