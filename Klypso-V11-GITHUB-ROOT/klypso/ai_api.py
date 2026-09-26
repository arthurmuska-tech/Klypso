import json
import re
import subprocess
import tempfile
from pathlib import Path

import requests
from flask import Blueprint, current_app, jsonify, session

from .auth import login_required
from .database import get_db
from .promo import effective_plan_key

ai_bp = Blueprint('ai_api', __name__)

def _headers():
    return {'Authorization': f"Bearer {current_app.config['AI_API_KEY']}"}

def _json(text):
    text = re.sub(r'^```json\\s*|\\s*```$', '', (text or '').strip(), flags=re.I)
    return json.loads(text)

def _transcribe(video_path):
    handle = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
    handle.close()
    audio = Path(handle.name)
    try:
        subprocess.run(['ffmpeg','-y','-i',video_path,'-vn','-ac','1','-ar','16000','-b:a','64k',str(audio)], check=True, capture_output=True, text=True)
        with audio.open('rb') as f:
            r = requests.post(
                f"{current_app.config['AI_API_BASE_URL']}/audio/transcriptions",
                headers=_headers(),
                files={'file': (audio.name, f, 'audio/mpeg')},
                data={'model': current_app.config['AI_TRANSCRIPTION_MODEL']},
                timeout=current_app.config['AI_API_TIMEOUT_SECONDS'],
            )
        r.raise_for_status()
        return r.json().get('text','')
    finally:
        audio.unlink(missing_ok=True)

def _analyze(transcript, duration, candidates):
    prompt = {'task':'Analyse une vidéo de streamer pour proposer les meilleurs moments à transformer en clips.','transcript':transcript[:30000],'duration_seconds':duration,'candidates':candidates[:30],'return_only_json':True,'schema':{'potential_score':0,'titles':['titre 1','titre 2','titre 3','titre 4','titre 5'],'hooks':['hook 1','hook 2','hook 3'],'best_candidate_ids':['c1'],'reasons':['raison']}}
    r = requests.post(
        f"{current_app.config['AI_API_BASE_URL']}/chat/completions",
        headers={**_headers(), 'Content-Type':'application/json'},
        json={'model':current_app.config['AI_TEXT_MODEL'],'messages':[{'role':'system','content':'Tu es un éditeur vidéo expert. Réponds uniquement avec du JSON valide.'},{'role':'user','content':json.dumps(prompt,ensure_ascii=False)}],'temperature':0.2},
        timeout=current_app.config['AI_API_TIMEOUT_SECONDS'],
    )
    r.raise_for_status()
    return _json(r.json()['choices'][0]['message']['content'])

@ai_bp.get('/api/ai/status')
@login_required
def status():
    with get_db(current_app.config['DATABASE_PATH']) as db:
        user = db.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone()
    plan = effective_plan_key(user)
    return jsonify({'plan':plan,'enabled':plan in {'pro','ultra'} and bool(current_app.config['AI_API_KEY'])})

@ai_bp.post('/api/ai/analyze/<int:job_id>')
@login_required
def analyze_job(job_id):
    with get_db(current_app.config['DATABASE_PATH']) as db:
        user = db.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone()
        job = db.execute('SELECT * FROM jobs WHERE id=? AND user_id=?',(job_id,session['user_id'])).fetchone()
    plan = effective_plan_key(user)
    if plan not in {'pro','ultra'}: return jsonify({'error':'L API IA est réservée aux plans Pro et Ultra.'}),403
    if not current_app.config['AI_API_KEY']: return jsonify({'error':'AI_API_KEY n est pas configurée sur le serveur.'}),503
    if not job: return jsonify({'error':'Projet introuvable.'}),404
    payload = json.loads(job['payload_json'] or '{}')
    path = payload.get('path')
    if not path or not Path(path).exists(): return jsonify({'error':'Vidéo introuvable.'}),404
    try:
        from .clips.analyzer import analyze_media
        from .clips.candidates import generate_candidates
        analysis = analyze_media(path)
        candidates = generate_candidates(analysis['duration'])
        transcript = _transcribe(path)
        ai = _analyze(transcript, analysis['duration'], candidates)
        result = {'mode':'api','transcript':transcript,'ai':ai,'analysis':analysis}
        with get_db(current_app.config['DATABASE_PATH']) as db:
            db.execute('UPDATE jobs SET status=?,result_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',('completed',json.dumps(result,ensure_ascii=False),job_id))
            db.commit()
        return jsonify({'ok':True,'result':result})
    except Exception:
        current_app.logger.exception('Pro/Ultra AI analysis failed')
        with get_db(current_app.config['DATABASE_PATH']) as db:
            db.execute('UPDATE jobs SET status=?,error_message=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',('failed','AI API analysis failed',job_id))
            db.commit()
        return jsonify({'error':'L analyse IA a échoué. Vérifie la configuration API du serveur.'}),500
