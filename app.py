"""
app.py - ATS Analyzer Production App
Routes: landing, login, signup, dashboard, analyze, history, compare, linkedin
"""
import os, io, json, base64, tempfile, subprocess
from functools import wraps
from flask import (Flask, render_template, request, jsonify,
                   session, redirect, url_for)
from analyzer import ATSAnalyzer
from linkedin_analyzer import LinkedInAnalyzer
from database import (init_db, create_user, get_user_by_email, get_user_by_id,
                      verify_password, save_analysis, get_user_analyses,
                      get_analysis_by_id, delete_analysis, get_user_stats,
                      update_profile, update_password,
                      save_reset_token, get_reset_token, mark_token_used)
from google_auth import google_auth as google_auth_blueprint

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY','ats-secret-change-in-prod-2025')
app.register_blueprint(google_auth_blueprint)

# Load .env file if it exists
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())
load_env()
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

ats_engine = ATSAnalyzer()
li_engine  = LinkedInAnalyzer()
IMAGE_EXT  = {'.jpg','.jpeg','.png','.webp','.bmp','.tiff','.tif'}

    

def login_required(f):
    @wraps(f)
    def dec(*a,**kw):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.path))
        return f(*a,**kw)
    return dec

def current_user():
    return get_user_by_id(session['user_id']) if 'user_id' in session else None

def pdf_to_images(raw, max_pages=6):
    try:
        from pdf2image import convert_from_bytes
        pages = convert_from_bytes(raw, dpi=150, first_page=1, last_page=max_pages)
        out = []
        for p in pages:
            buf = io.BytesIO(); p.save(buf,'PNG',optimize=True)
            out.append(base64.b64encode(buf.getvalue()).decode())
        return out
    except: return []

def docx_to_images(raw, max_pages=6):
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dp = os.path.join(tmp,'resume.docx')
            open(dp,'wb').write(raw)
            subprocess.run(['libreoffice','--headless','--convert-to','pdf','--outdir',tmp,dp],
                           capture_output=True,timeout=30)
            pp = os.path.join(tmp,'resume.pdf')
            if not os.path.exists(pp): return []
            return pdf_to_images(open(pp,'rb').read(), max_pages)
    except: return []

def img_to_b64(raw):
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw))
        if img.width>1200: img=img.resize((1200,int(img.height*1200/img.width)))
        buf=io.BytesIO(); img.save(buf,'PNG',optimize=True)
        return [base64.b64encode(buf.getvalue()).decode()]
    except: return []

# ── Pages ─────────────────────────────────────────────────────
@app.route('/')
def landing():
    return render_template('landing.html', user=current_user())

@app.route('/login', methods=['GET','POST'])
def login():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method=='POST':
        u = get_user_by_email(request.form.get('email',''))
        if u and verify_password(request.form.get('password',''), u['password']):
            session['user_id']=u['id']; session['user_name']=u['name']
            return redirect(request.args.get('next', url_for('dashboard')))
        return render_template('login.html', error='Invalid email or password.')
    return render_template('login.html')

@app.route('/signup', methods=['GET','POST'])
def signup():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method=='POST':
        name=request.form.get('name','').strip()
        email=request.form.get('email','').strip()
        pw=request.form.get('password','')
        confirm=request.form.get('confirm','')
        if not name or not email or not pw:
            return render_template('signup.html', error='All fields are required.')
        if len(pw)<6:
            return render_template('signup.html', error='Password must be at least 6 characters.')
        if pw!=confirm:
            return render_template('signup.html', error='Passwords do not match.')
        r=create_user(name,email,pw)
        if r['success']:
            u=get_user_by_email(email)
            session['user_id']=u['id']; session['user_name']=u['name']
            return redirect(url_for('dashboard'))
        return render_template('signup.html', error=r.get('error','Signup failed.'))
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('landing'))

@app.route('/dashboard')
@login_required
def dashboard():
    u=current_user()
    return render_template('dashboard.html', user=u,
                           analyses=get_user_analyses(u['id'])[:6],
                           stats=get_user_stats(u['id']))

@app.route('/analyze')
@login_required
def analyze_page():
    return render_template('analyzer.html', user=current_user())

@app.route('/history')
@login_required
def history():
    u=current_user()
    return render_template('history.html', user=u, analyses=get_user_analyses(u['id']))

@app.route('/history/<int:aid>')
@login_required
def view_analysis(aid):
    u=current_user()
    a=get_analysis_by_id(aid,u['id'])
    if not a: return redirect(url_for('history'))
    return render_template('view_analysis.html', user=u, analysis=a)

@app.route('/compare')
@login_required
def compare():
    u=current_user()
    return render_template('compare.html', user=u, analyses=get_user_analyses(u['id']))

@app.route('/linkedin')
@login_required
def linkedin_page():
    return render_template('linkedin.html', user=current_user())

# ── APIs ──────────────────────────────────────────────────────
@app.route('/api/analyze', methods=['POST'])
@login_required
def api_analyze():
    u=current_user()
    jd=request.form.get('job_description','').strip()
    role=request.form.get('role','general').strip()
    resume_text=''; resume_name='Resume'; method='text'; preview=[]

    if 'resume_file' in request.files and request.files['resume_file'].filename:
        f=request.files['resume_file']
        resume_name=f.filename
        ext=os.path.splitext(f.filename.lower())[1]
        raw=f.read()
        try:
            if ext=='.pdf':
                resume_text=ats_engine.extract_pdf(io.BytesIO(raw)); method='pdf'; preview=pdf_to_images(raw)
            elif ext=='.docx':
                resume_text=ats_engine.extract_docx(io.BytesIO(raw)); method='docx'; preview=docx_to_images(raw)
            elif ext in IMAGE_EXT:
                resume_text=ats_engine.extract_image(io.BytesIO(raw)); method='ocr_image'; preview=img_to_b64(raw)
            else:
                return jsonify({'error':f"Unsupported file type '{ext}'."}),400
        except (ImportError,ValueError) as e:
            return jsonify({'error':str(e)}),400
        except Exception as e:
            return jsonify({'error':f'Could not read file: {e}'}),500
    elif request.form.get('resume_text','').strip():
        resume_text=request.form.get('resume_text','').strip()
    else:
        return jsonify({'error':'Please upload a file or paste resume text.'}),400

    if len(resume_text)<50:
        return jsonify({'error':'Resume content too short or could not be extracted.'}),400

    try:
        result=ats_engine.analyze(resume_text,jd,role)
        result.update({'extraction_method':method,'resume_text':resume_text,
                       'preview_images':preview,'job_description':jd})
        result['role']=role
        result['analysis_id']=save_analysis(u['id'],result,resume_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error':f'Analysis failed: {e}'}),500

@app.route('/api/linkedin', methods=['POST'])
@login_required
def api_linkedin():
    profile=( request.get_json() or {} ).get('profile_text','').strip()
    if len(profile)<50:
        return jsonify({'error':'Paste at least 50 characters from your LinkedIn profile.'}),400
    try:
        return jsonify(li_engine.analyze(profile))
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/delete/<int:aid>', methods=['DELETE'])
@login_required
def api_delete(aid):
    delete_analysis(aid, current_user()['id'])
    return jsonify({'success':True})

@app.route('/api/compare', methods=['POST'])
@login_required
def api_compare():
    u=current_user(); d=request.get_json() or {}
    a1=get_analysis_by_id(d.get('id1'),u['id'])
    a2=get_analysis_by_id(d.get('id2'),u['id'])
    if not a1 or not a2: return jsonify({'error':'Analyses not found.'}),404
    return jsonify({'a1':a1,'a2':a2})


import datetime

@app.route('/forgot-password', methods=['GET','POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email','').strip().lower()
        user = get_user_by_email(email)
        if user:
            import secrets
            token = secrets.token_urlsafe(32)
            expires = (datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat()
            save_reset_token(email, token, expires)
            reset_url = url_for('reset_password', token=token, _external=True)
            return render_template('forgot_password.html', success=True, reset_url=reset_url, email=email)
        return render_template('forgot_password.html', success=True, email=email)
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET','POST'])
def reset_password(token):
    record = get_reset_token(token)
    if not record:
        return render_template('reset_password.html', error='Invalid or expired reset link.')
    try:
        expires = datetime.datetime.fromisoformat(record['expires_at'])
        if datetime.datetime.now() > expires:
            return render_template('reset_password.html', error='Link expired. Request a new one.')
    except:
        return render_template('reset_password.html', error='Invalid reset link.')
    if request.method == 'POST':
        pw  = request.form.get('password','')
        pw2 = request.form.get('confirm','')
        if len(pw) < 6:
            return render_template('reset_password.html', token=token, error='Password must be at least 6 characters.')
        if pw != pw2:
            return render_template('reset_password.html', token=token, error='Passwords do not match.')
        user = get_user_by_email(record['email'])
        if user:
            update_password(user['id'], pw)
            mark_token_used(token)
            return render_template('reset_password.html', success=True)
        return render_template('reset_password.html', token=token, error='Account not found.')
    return render_template('reset_password.html', token=token)

@app.route('/profile', methods=['GET','POST'])
@login_required
def profile():
    user = current_user()
    success_msg = ''
    error_msg = ''
    if request.method == 'POST':
        action = request.form.get('action','')
        if action == 'update_profile':
            name  = request.form.get('name','').strip()
            email = request.form.get('email','').strip()
            if not name or not email:
                error_msg = 'Name and email are required.'
            else:
                result = update_profile(user['id'], name, email)
                if result['success']:
                    session['user_name'] = name
                    success_msg = 'Profile updated successfully!'
                    user = current_user()
                else:
                    error_msg = result.get('error','Update failed.')
        elif action == 'change_password':
            current_pw = request.form.get('current_password','')
            new_pw     = request.form.get('new_password','')
            confirm_pw = request.form.get('confirm_password','')
            if not verify_password(current_pw, user['password']):
                error_msg = 'Current password is incorrect.'
            elif len(new_pw) < 6:
                error_msg = 'New password must be at least 6 characters.'
            elif new_pw != confirm_pw:
                error_msg = 'New passwords do not match.'
            else:
                result = update_password(user['id'], new_pw)
                if result['success']:
                    success_msg = 'Password changed successfully!'
                else:
                    error_msg = result.get('error','Password change failed.')
    stats = get_user_stats(user['id'])
    return render_template('profile.html', user=user, stats=stats, success=success_msg, error=error_msg)

if __name__=='__main__':
    app.run(host='0.0.0.0',port=5002,debug=True)
