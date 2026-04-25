from __future__ import annotations

import argparse
import html
import importlib
import io
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.request import urlretrieve

from flask import Flask, jsonify, render_template, request, send_file, url_for
from googletrans import LANGUAGES, Translator
from PyPDF2 import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from werkzeug.utils import secure_filename

try:
    deep_translator_module = importlib.import_module("deep_translator")
    DeepGoogleTranslator = getattr(deep_translator_module, "GoogleTranslator", None)
except Exception:
    DeepGoogleTranslator = None

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024

FONTS_DIR = Path("fonts")
URL_COM = "translate.googleapis.com"
DEFAULT_CHUNK_SIZE = 2400
MAX_RETRIES = 3
MAX_JOB_HISTORY = 24

FONT_ASSETS = {
    "NotoSans-Regular.ttf": "https://raw.githubusercontent.com/notofonts/noto-fonts/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf",
    "NotoSans-Bold.ttf": "https://raw.githubusercontent.com/notofonts/noto-fonts/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf",
    "NotoSansDevanagari-Regular.ttf": "https://raw.githubusercontent.com/notofonts/noto-fonts/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Regular.ttf",
    "NotoSansTamil-Regular.ttf": "https://raw.githubusercontent.com/notofonts/noto-fonts/main/hinted/ttf/NotoSansTamil/NotoSansTamil-Regular.ttf",
    "NotoSansBengali-Regular.ttf": "https://raw.githubusercontent.com/notofonts/noto-fonts/main/hinted/ttf/NotoSansBengali/NotoSansBengali-Regular.ttf",
    "NotoSansGujarati-Regular.ttf": "https://raw.githubusercontent.com/notofonts/noto-fonts/main/hinted/ttf/NotoSansGujarati/NotoSansGujarati-Regular.ttf",
    "NotoSansGurmukhi-Regular.ttf": "https://raw.githubusercontent.com/notofonts/noto-fonts/main/hinted/ttf/NotoSansGurmukhi/NotoSansGurmukhi-Regular.ttf",
    "NotoSansKannada-Regular.ttf": "https://raw.githubusercontent.com/notofonts/noto-fonts/main/hinted/ttf/NotoSansKannada/NotoSansKannada-Regular.ttf",
    "NotoSansMalayalam-Regular.ttf": "https://raw.githubusercontent.com/notofonts/noto-fonts/main/hinted/ttf/NotoSansMalayalam/NotoSansMalayalam-Regular.ttf",
    "NotoSansTelugu-Regular.ttf": "https://raw.githubusercontent.com/notofonts/noto-fonts/main/hinted/ttf/NotoSansTelugu/NotoSansTelugu-Regular.ttf",
    "NotoNaskhArabic-Regular.ttf": "https://raw.githubusercontent.com/notofonts/noto-fonts/main/hinted/ttf/NotoNaskhArabic/NotoNaskhArabic-Regular.ttf",
}

FONT_REGISTRY = {
    "NotoSans": "NotoSans-Regular.ttf",
    "NotoSansBold": "NotoSans-Bold.ttf",
    "NotoSansDevanagari": "NotoSansDevanagari-Regular.ttf",
    "NotoSansTamil": "NotoSansTamil-Regular.ttf",
    "NotoSansBengali": "NotoSansBengali-Regular.ttf",
    "NotoSansGujarati": "NotoSansGujarati-Regular.ttf",
    "NotoSansGurmukhi": "NotoSansGurmukhi-Regular.ttf",
    "NotoSansKannada": "NotoSansKannada-Regular.ttf",
    "NotoSansMalayalam": "NotoSansMalayalam-Regular.ttf",
    "NotoSansTelugu": "NotoSansTelugu-Regular.ttf",
    "NotoNaskhArabic": "NotoNaskhArabic-Regular.ttf",
}

SYSTEM_FONT_CANDIDATES = {
    "NirmalaUI": Path("C:/Windows/Fonts/Nirmala.ttf"),
    "Mangal": Path("C:/Windows/Fonts/mangal.ttf"),
    "Latha": Path("C:/Windows/Fonts/latha.ttf"),
}

LANGUAGE_FONT_MAP = {
    "hi": "NotoSansDevanagari",
    "mr": "NotoSansDevanagari",
    "ne": "NotoSansDevanagari",
    "sa": "NotoSansDevanagari",
    "ta": "NotoSansTamil",
    "te": "NotoSansTelugu",
    "kn": "NotoSansKannada",
    "ml": "NotoSansMalayalam",
    "gu": "NotoSansGujarati",
    "bn": "NotoSansBengali",
    "pa": "NotoSansGurmukhi",
    "ur": "NotoNaskhArabic",
    "ar": "NotoNaskhArabic",
    "fa": "NotoNaskhArabic",
}

jobs_lock = threading.Lock()
jobs: dict[str, dict] = {}

fonts_lock = threading.Lock()
registered_fonts: set[str] = set()
fonts_loaded = False


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(value, max_value))


def ensure_fonts() -> None:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    for file_name, url in FONT_ASSETS.items():
        destination = FONTS_DIR / file_name
        if destination.exists():
            continue
        try:
            urlretrieve(url, destination)
        except Exception:
            # Continue even if some fonts fail to download.
            pass


def register_font(font_name: str, font_path: Path) -> bool:
    if not font_path.exists():
        return False
    try:
        pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
        return True
    except Exception:
        return False


def load_registered_fonts() -> set[str]:
    global fonts_loaded
    with fonts_lock:
        if fonts_loaded:
            return set(registered_fonts)

        ensure_fonts()

        for font_name, file_name in FONT_REGISTRY.items():
            if register_font(font_name, FONTS_DIR / file_name):
                registered_fonts.add(font_name)

        for font_name, file_path in SYSTEM_FONT_CANDIDATES.items():
            if register_font(font_name, file_path):
                registered_fonts.add(font_name)

        fonts_loaded = True
        return set(registered_fonts)


def get_font_for_language(lang_code: str, fonts: set[str]) -> str:
    base_code = lang_code.lower().split("-")[0]
    preferred = LANGUAGE_FONT_MAP.get(base_code, "NotoSans")
    fallbacks = [preferred, "NirmalaUI", "Mangal", "NotoSans", "Helvetica"]

    for font_name in fallbacks:
        if font_name == "Helvetica" or font_name in fonts:
            return font_name
    return "Helvetica"


def build_styles(body_font: str, heading_font: str) -> tuple[ParagraphStyle, ParagraphStyle, ParagraphStyle]:
    style_sheet = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "BodyStyle",
        parent=style_sheet["Normal"],
        fontName=body_font,
        fontSize=11,
        leading=18,
        firstLineIndent=10,
        spaceAfter=9,
        splitLongWords=True,
    )
    page_header_style = ParagraphStyle(
        "PageHeaderStyle",
        parent=style_sheet["Normal"],
        fontName=heading_font,
        fontSize=12,
        textColor="#0f766e",
        spaceAfter=8,
    )
    note_style = ParagraphStyle(
        "NoteStyle",
        parent=style_sheet["Normal"],
        fontName=body_font,
        fontSize=9.5,
        textColor="#475569",
    )
    return body_style, page_header_style, note_style


def split_large_text(text: str, max_chars: int) -> list[str]:
    normalized = re.sub(r"\r\n?", "\n", text).strip()
    if not normalized:
        return []

    chunks: list[str] = []
    current = ""
    paragraphs = [p.strip() for p in normalized.split("\n\n") if p.strip()]

    for paragraph in paragraphs:
        sentence_parts = re.split(r"(?<=[.!?])\s+", paragraph) if len(paragraph) > max_chars else [paragraph]
        for part in sentence_parts:
            part = part.strip()
            if not part:
                continue

            if len(part) > max_chars:
                words = part.split()
                rolling = ""
                for word in words:
                    candidate = f"{rolling} {word}".strip()
                    if len(candidate) <= max_chars:
                        rolling = candidate
                    else:
                        if rolling:
                            chunks.append(rolling)
                        rolling = word
                if rolling:
                    chunks.append(rolling)
                continue

            candidate = f"{current}\n\n{part}".strip() if current else part
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = part

    if current:
        chunks.append(current)
    return chunks


def normalize_deep_target(lang_code: str) -> str:
    special_map = {
        "zh-cn": "zh-CN",
        "zh-tw": "zh-TW",
    }
    return special_map.get(lang_code.lower(), lang_code)


def translate_with_googletrans(client: Translator, text: str, target_lang: str) -> Optional[str]:
    try:
        result = client.translate(text, dest=target_lang)
        translated = getattr(result, "text", "")
        if translated and translated.strip():
            return translated
        return None
    except Exception:
        return None


def translate_with_deep_translator(text: str, target_lang: str) -> Optional[str]:
    if DeepGoogleTranslator is None:
        return None
    try:
        translator = DeepGoogleTranslator(source="auto", target=normalize_deep_target(target_lang))
        translated = translator.translate(text)
        if translated and translated.strip():
            return translated
        return None
    except Exception:
        return None


def robust_translate_chunk(
    client: Translator,
    text: str,
    target_lang: str,
    use_fallback_engine: bool,
) -> tuple[str, str]:
    for attempt in range(1, MAX_RETRIES + 1):
        translated = translate_with_googletrans(client, text, target_lang)
        if translated:
            return translated, "googletrans"
        time.sleep(0.18 * attempt)

    if use_fallback_engine:
        backup = translate_with_deep_translator(text, target_lang)
        if backup:
            return backup, "deep-translator"

    return text, "fallback"


def translate_pages(
    pdf_bytes: bytes,
    lang_code: str,
    max_chars: int,
    use_fallback_engine: bool,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> tuple[list[str], dict[str, int]]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise ValueError("Encrypted PDF needs a password and is not supported in this demo.") from exc

    total_pages = len(reader.pages)
    stats = {
        "total_pages": total_pages,
        "text_pages": 0,
        "total_chunks": 0,
        "google_chunks": 0,
        "deep_chunks": 0,
        "fallback_chunks": 0,
    }

    translated_pages: list[str] = []
    translator_client = Translator(service_urls=[URL_COM])

    for page_index, page in enumerate(reader.pages, start=1):
        source_text = (page.extract_text() or "").strip()
        if not source_text:
            translated_pages.append("")
            if on_progress:
                on_progress(page_index, total_pages)
            continue

        stats["text_pages"] += 1
        chunks = split_large_text(source_text, max_chars=max_chars)
        translated_chunks: list[str] = []

        for chunk in chunks:
            stats["total_chunks"] += 1
            translated_chunk, engine = robust_translate_chunk(
                translator_client,
                chunk,
                lang_code,
                use_fallback_engine=use_fallback_engine,
            )
            translated_chunks.append(translated_chunk)
            if engine == "googletrans":
                stats["google_chunks"] += 1
            elif engine == "deep-translator":
                stats["deep_chunks"] += 1
            else:
                stats["fallback_chunks"] += 1

        translated_pages.append("\n\n".join(translated_chunks).strip())
        if on_progress:
            on_progress(page_index, total_pages)

    return translated_pages, stats


def build_translated_pdf(
    translated_pages: list[str],
    source_name: str,
    target_lang: str,
    body_font: str,
    heading_font: str,
) -> bytes:
    body_style, header_style, note_style = build_styles(body_font, heading_font)
    buffer = io.BytesIO()
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=48,
        rightMargin=48,
        topMargin=48,
        bottomMargin=42,
        title=f"Translated - {source_name}",
        author="PDF Translator Pro",
        creator="Flask",
        subject=f"Translated to {target_lang}",
    )

    story = []
    for page_number, text in enumerate(translated_pages, start=1):
        story.append(Paragraph(f"Page {page_number}", header_style))
        story.append(Paragraph(f"Generated: {generated_at}", note_style))
        story.append(Spacer(1, 8))

        if text:
            paragraphs = [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
            for chunk in paragraphs:
                safe_chunk = html.escape(chunk).replace("\n", "<br/>")
                story.append(Paragraph(safe_chunk, body_style))
        else:
            story.append(Paragraph("No extractable text was found on this page.", note_style))

        if page_number < len(translated_pages):
            story.append(PageBreak())

    document.build(story)
    buffer.seek(0)
    return buffer.read()


def first_preview_text(pages: list[str], limit: int = 2400) -> str:
    for page in pages:
        if page and page.strip():
            return page[:limit]
    return "No translatable text was extracted from this file."


def prune_old_jobs() -> None:
    with jobs_lock:
        if len(jobs) <= MAX_JOB_HISTORY:
            return
        ordered = sorted(jobs.items(), key=lambda item: item[1].get("created_ts", 0.0))
        for job_id, _ in ordered[: len(jobs) - MAX_JOB_HISTORY]:
            jobs.pop(job_id, None)


def update_job(job_id: str, **updates: object) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        job.update(updates)
        job["updated_at"] = utc_iso_now()


def build_job_payload(job_id: str, job: dict) -> dict:
    payload = {
        "job_id": job_id,
        "status": job.get("status"),
        "progress": int(job.get("progress", 0)),
        "message": job.get("message", ""),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "target_language": job.get("target_language"),
        "target_language_name": LANGUAGES.get(str(job.get("target_language", "")), "Unknown").title(),
        "font": job.get("font"),
        "stats": job.get("stats", {}),
        "preview": job.get("preview", ""),
        "source_name": job.get("source_name", ""),
    }

    if job.get("status") == "completed":
        payload["download_url"] = url_for("download_job_result", job_id=job_id)
        payload["output_name"] = job.get("output_name", "translated.pdf")

    if job.get("status") == "failed":
        payload["error"] = job.get("error", "Unknown error")

    return payload


def process_translation_job(
    job_id: str,
    pdf_bytes: bytes,
    source_name: str,
    target_lang: str,
    chunk_size: int,
    use_fallback_engine: bool,
) -> None:
    try:
        update_job(
            job_id,
            status="running",
            progress=2,
            message="Preparing fonts and translation engine...",
        )

        fonts = load_registered_fonts()
        body_font = get_font_for_language(target_lang, fonts)
        heading_font = "NotoSansBold" if "NotoSansBold" in fonts else body_font
        update_job(job_id, font=body_font)

        def on_progress(current: int, total: int) -> None:
            if total <= 0:
                percent = 20
            else:
                percent = 5 + int((current / total) * 82)
            update_job(
                job_id,
                progress=min(percent, 90),
                message=f"Translating page {current} of {total}...",
            )

        translated_pages, stats = translate_pages(
            pdf_bytes,
            target_lang,
            max_chars=chunk_size,
            use_fallback_engine=use_fallback_engine,
            on_progress=on_progress,
        )

        update_job(job_id, progress=94, message="Building translated PDF output...")
        output_pdf = build_translated_pdf(
            translated_pages,
            source_name,
            target_lang,
            body_font=body_font,
            heading_font=heading_font,
        )

        output_name = f"translated_{target_lang}_{Path(source_name).stem}.pdf"
        update_job(
            job_id,
            status="completed",
            progress=100,
            message="Translation completed successfully.",
            stats=stats,
            preview=first_preview_text(translated_pages),
            output_pdf=output_pdf,
            output_name=output_name,
        )
    except Exception as exc:
        update_job(
            job_id,
            status="failed",
            progress=100,
            message="Translation failed.",
            error=str(exc),
        )


def validate_pdf(pdf_bytes: bytes) -> tuple[bool, Optional[str], int]:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                return False, "Encrypted PDF is not supported without password.", 0

        pages = len(reader.pages)
        if pages <= 0:
            return False, "Uploaded PDF has no pages.", 0
        return True, None, pages
    except Exception:
        return False, "Could not read PDF. Upload a valid text-based PDF file.", 0


def translated_language_options() -> list[dict[str, str]]:
    options = []
    for code, name in sorted(LANGUAGES.items(), key=lambda item: item[1]):
        options.append({"code": code, "name": name.title()})
    return options


def language_font_matrix() -> list[dict[str, str]]:
    fonts = load_registered_fonts()
    matrix = []
    for item in translated_language_options():
        matrix.append(
            {
                "code": item["code"],
                "name": item["name"],
                "font": get_font_for_language(item["code"], fonts),
            }
        )
    return matrix


@app.get("/")
def index():
    options = translated_language_options()
    default_lang = "hi" if "hi" in LANGUAGES else options[0]["code"]
    return render_template(
        "index.html",
        languages=options,
        font_map=language_font_matrix(),
        default_lang=default_lang,
        default_chunk_size=DEFAULT_CHUNK_SIZE,
    )


@app.post("/api/sample-translate")
def sample_translate():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    target_lang = str(payload.get("target_lang", "")).strip().lower()
    use_fallback_engine = parse_bool(str(payload.get("use_fallback_engine", "true")), default=True)

    if not text:
        return jsonify({"error": "Please enter text to translate."}), 400
    if target_lang not in LANGUAGES:
        return jsonify({"error": "Unsupported language code."}), 400

    client = Translator(service_urls=[URL_COM])
    translated, engine = robust_translate_chunk(client, text, target_lang, use_fallback_engine)
    return jsonify({"translated_text": translated, "engine": engine})


@app.post("/api/jobs")
def create_job():
    file = request.files.get("pdf")
    if file is None:
        return jsonify({"error": "PDF file is required."}), 400

    target_lang = str(request.form.get("target_lang", "")).strip().lower()
    if target_lang not in LANGUAGES:
        return jsonify({"error": "Unsupported language code."}), 400

    if not file.filename:
        return jsonify({"error": "Invalid file name."}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are allowed."}), 400

    file_name = secure_filename(file.filename) or "uploaded.pdf"
    pdf_bytes = file.read()
    if not pdf_bytes:
        return jsonify({"error": "Uploaded file is empty."}), 400

    is_valid, error_message, total_pages = validate_pdf(pdf_bytes)
    if not is_valid:
        return jsonify({"error": error_message}), 400

    try:
        chunk_size = int(str(request.form.get("chunk_size", DEFAULT_CHUNK_SIZE)))
    except ValueError:
        chunk_size = DEFAULT_CHUNK_SIZE
    chunk_size = clamp(chunk_size, 1200, 4200)

    use_fallback_engine = parse_bool(request.form.get("use_fallback_engine"), default=True)

    prune_old_jobs()
    job_id = uuid.uuid4().hex
    now = utc_iso_now()

    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "progress": 0,
            "message": "Job queued. Waiting to start...",
            "created_at": now,
            "updated_at": now,
            "created_ts": time.time(),
            "source_name": file_name,
            "target_language": target_lang,
            "font": "Pending",
            "preview": "",
            "stats": {
                "total_pages": total_pages,
                "text_pages": 0,
                "total_chunks": 0,
                "google_chunks": 0,
                "deep_chunks": 0,
                "fallback_chunks": 0,
            },
        }

    worker = threading.Thread(
        target=process_translation_job,
        args=(job_id, pdf_bytes, file_name, target_lang, chunk_size, use_fallback_engine),
        daemon=True,
    )
    worker.start()

    return (
        jsonify(
            {
                "job_id": job_id,
                "status_url": url_for("get_job_status", job_id=job_id),
                "download_url": url_for("download_job_result", job_id=job_id),
                "total_pages": total_pages,
            }
        ),
        202,
    )


@app.get("/api/jobs/<job_id>")
def get_job_status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found."}), 404

    return jsonify(build_job_payload(job_id, job))


@app.get("/api/jobs/<job_id>/download")
def download_job_result(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found."}), 404

    if job.get("status") != "completed":
        return jsonify({"error": "Translation is not complete yet."}), 409

    output_pdf = job.get("output_pdf")
    output_name = str(job.get("output_name", "translated.pdf"))
    if not output_pdf:
        return jsonify({"error": "Output file not available."}), 500

    return send_file(
        io.BytesIO(output_pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=output_name,
    )


@app.get("/api/languages")
def list_languages():
    return jsonify(
        {
            "languages": translated_language_options(),
            "font_map": language_font_matrix(),
        }
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run PDF Translator Pro server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface")
    parser.add_argument("--port", type=int, default=5000, help="Port number")
    parser.add_argument(
        "--no-debug",
        action="store_true",
        help="Run Flask without debug mode",
    )
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=not args.no_debug)
