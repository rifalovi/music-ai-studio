"""API HTTP du POC — pilote le loop depuis l'UI web.

Deux endpoints :
    POST /analyze  — upload d'un fichier -> profil chiffré (sans traitement)
    POST /master   — upload + intention  -> avant / décision / après + fichier traité
    GET  /outputs/<name> — récupère le fichier masterisé

Lancement :  uvicorn server:app --reload
"""

from __future__ import annotations

import os
import uuid

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from analysis import analyze
from pipeline import master

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE, "_uploads")
OUTPUT_DIR = os.path.join(BASE, "_outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(title="Console de mixage augmentée IA — POC")

# En dev, l'UI statique et l'API sont servies séparément (d'où le CORS ouvert).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")


def _save_upload(upload: UploadFile) -> str:
    ext = os.path.splitext(upload.filename or "")[1] or ".wav"
    path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{ext}")
    with open(path, "wb") as fh:
        fh.write(upload.file.read())
    return path


@app.post("/analyze")
async def analyze_endpoint(file: UploadFile = File(...)):
    path = _save_upload(file)
    return JSONResponse(analyze(path).model_dump())


@app.post("/master")
async def master_endpoint(
    file: UploadFile = File(...),
    intent: str = Form(""),
    target_lufs: float = Form(-14.0),
):
    in_path = _save_upload(file)
    out_name = f"{uuid.uuid4().hex}.wav"
    out_path = os.path.join(OUTPUT_DIR, out_name)
    result = master(in_path, out_path, intent=intent, target_lufs=target_lufs)
    payload = result.to_dict()
    payload["output_url"] = f"/outputs/{out_name}"
    return JSONResponse(payload)


@app.get("/outputs/{name}")
async def get_output(name: str):
    # Garde-fou anti-traversée de chemin.
    safe = os.path.basename(name)
    path = os.path.join(OUTPUT_DIR, safe)
    if not os.path.isfile(path):
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path, media_type="audio/wav")
