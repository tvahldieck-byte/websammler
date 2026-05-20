import os
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify
)
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv
from models import db, Bereich, Kategorie, Datensatz
from services.metadata import analyze_url

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-bitte-aendern')

# Datenbank
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('DATA_DIR', BASE_DIR)
db_path = os.path.join(DATA_DIR, 'app.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)


# ─────────────────────────────────────────────
# Jinja2 Custom Filter
# ─────────────────────────────────────────────

@app.template_filter('merge')
def merge_filter(d, updates):
    """Merged zwei Dicts – für URL-Parameter-Manipulation im Template."""
    result = dict(d)
    result.update(updates)
    return {k: v for k, v in result.items() if v != '' and v is not None}


# ─────────────────────────────────────────────
# Login-Manager
# ─────────────────────────────────────────────

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Bitte anmelden.'


class DummyUser(UserMixin):
    id = 1


dummy_user = DummyUser()


@login_manager.user_loader
def load_user(user_id):
    if str(user_id) == '1':
        return dummy_user
    return None


def verify_password(eingabe: str) -> bool:
    """Prüft das eingegebene Passwort – unterstützt Hash-File und Env-Variable."""
    hash_file = os.path.join(DATA_DIR, 'password.hash')
    if os.path.exists(hash_file):
        try:
            with open(hash_file) as f:
                stored = f.read().strip()
            return check_password_hash(stored, eingabe.strip())
        except Exception:
            pass
    # Direkter Vergleich mit APP_PASSWORD (beide Seiten bereinigt)
    env_pw = os.environ.get('APP_PASSWORD', 'admin').strip()
    return eingabe.strip() == env_pw


def save_password_hash(pw_hash: str):
    hash_file = os.path.join(DATA_DIR, 'password.hash')
    with open(hash_file, 'w') as f:
        f.write(pw_hash)


# ─────────────────────────────────────────────
# Temporäre Debug-Route (wird nach Test entfernt)
# ─────────────────────────────────────────────

@app.route('/debug-pw')
def debug_pw():
    env_pw = os.environ.get('APP_PASSWORD', 'NICHT GESETZT')
    hash_file = os.path.join(DATA_DIR, 'password.hash')
    hash_exists = os.path.exists(hash_file)
    return (
        f"APP_PASSWORD Länge: {len(env_pw)} Zeichen | "
        f"Erste 2 Zeichen: '{env_pw[:2]}' | "
        f"Letzte 2 Zeichen: '{env_pw[-2:]}' | "
        f"Hash-File vorhanden: {hash_exists}"
    )


# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        pw = request.form.get('password', '')
        if verify_password(pw):
            login_user(dummy_user, remember=True)
            return redirect(request.args.get('next') or url_for('dashboard'))
        error = 'Falsches Passwort.'
    return render_template('login.html', error=error)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ─────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────

@app.route('/')
@login_required
def dashboard():
    bereiche = Bereich.query.order_by(Bereich.reihenfolge, Bereich.name).all()

    # Bereich auswählen – kein "Alle", immer einen Bereich aktiv
    bereich_id = request.args.get('bereich', type=int)
    if not bereich_id and bereiche:
        # Automatisch ersten Bereich vorauswählen
        return redirect(url_for('dashboard', bereich=bereiche[0].id))

    # Kategorien des aktiven Bereichs
    aktiver_bereich_obj = None
    kategorien = []
    if bereich_id:
        aktiver_bereich_obj = Bereich.query.get(bereich_id)
        if aktiver_bereich_obj:
            kategorien = Kategorie.query.filter_by(bereich_id=bereich_id)\
                                        .order_by(Kategorie.name).all()

    # Filter-Parameter
    kat_ids = request.args.getlist('kat', type=int)
    suche = request.args.get('q', '').strip()
    bildqualitaet = request.args.get('bq', type=int)
    laenge_von = request.args.get('lv', type=int)
    laenge_bis = request.args.get('lb', type=int)
    provider_filter = request.args.get('prov', '').strip()
    sort_by = request.args.get('sort', 'datum')
    sort_dir = request.args.get('dir', 'desc')

    query = Datensatz.query

    # Immer nach Bereich filtern
    if bereich_id:
        query = query.filter(Datensatz.bereich_id == bereich_id)

    if kat_ids:
        for kid in kat_ids:
            query = query.filter(Datensatz.kategorien.any(Kategorie.id == kid))

    if suche:
        query = query.filter(Datensatz.titel.ilike(f'%{suche}%'))

    if bildqualitaet:
        query = query.filter(Datensatz.bildqualitaet == bildqualitaet)

    if laenge_von is not None:
        query = query.filter(Datensatz.laenge_min >= laenge_von)
    if laenge_bis is not None:
        query = query.filter(Datensatz.laenge_min <= laenge_bis)

    if provider_filter:
        query = query.filter(Datensatz.provider == provider_filter)

    # Sortierung
    sort_map = {
        'titel': Datensatz.titel,
        'provider': Datensatz.provider,
        'bildqualitaet': Datensatz.bildqualitaet,
        'laenge_min': Datensatz.laenge_min,
        'aufrufe': Datensatz.aufrufe,
        'datum': Datensatz.datum,
        'bewertung': Datensatz.bewertung,
    }
    sort_col = sort_map.get(sort_by, Datensatz.datum)
    query = query.order_by(sort_col.asc() if sort_dir == 'asc' else sort_col.desc())

    datensaetze = query.all()

    # Provider-Liste für Filter-Dropdown (aus aktuellem Bereich)
    providers = sorted({
        ds.provider for ds in
        Datensatz.query.filter_by(bereich_id=bereich_id).all()
        if ds.provider
    })

    return render_template(
        'dashboard.html',
        datensaetze=datensaetze,
        bereiche=bereiche,
        kategorien=kategorien,
        aktiver_bereich=bereich_id,
        aktiver_bereich_obj=aktiver_bereich_obj,
        aktive_kats=kat_ids,
        suche=suche,
        bildqualitaet=bildqualitaet,
        laenge_von=laenge_von,
        laenge_bis=laenge_bis,
        provider_filter=provider_filter,
        providers=providers,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


# ─────────────────────────────────────────────
# API: URL analysieren
# ─────────────────────────────────────────────

@app.route('/api/url-info', methods=['POST'])
@login_required
def api_url_info():
    data = request.get_json()
    url = (data or {}).get('url', '').strip()
    if not url:
        return jsonify({'error': 'Keine URL'}), 400
    info = analyze_url(url)
    return jsonify(info)


# ─────────────────────────────────────────────
# API: Kategorien für einen Bereich
# ─────────────────────────────────────────────

@app.route('/api/kategorien')
@login_required
def api_kategorien():
    bereich_id = request.args.get('bereich_id', type=int)
    if not bereich_id:
        return jsonify([])
    kats = Kategorie.query.filter_by(bereich_id=bereich_id)\
                          .order_by(Kategorie.name).all()
    return jsonify([{'id': k.id, 'name': k.name} for k in kats])


# ─────────────────────────────────────────────
# Datensatz: Neu
# ─────────────────────────────────────────────

@app.route('/neu', methods=['GET', 'POST'])
@login_required
def neu():
    bereiche = Bereich.query.order_by(Bereich.reihenfolge, Bereich.name).all()
    # Bereich aus Dashboard-Kontext übernehmen
    vorgewaehlter_bereich = request.args.get('bereich', type=int)

    if request.method == 'POST':
        bereich_id = request.form.get('bereich_id', type=int) or None
        kat_ids = request.form.getlist('kategorien', type=int)
        ds = Datensatz(
            url=request.form.get('url', '').strip(),
            provider=request.form.get('provider', '').strip(),
            thumbnail_url=request.form.get('thumbnail_url', '').strip(),
            titel=request.form.get('titel', '').strip(),
            bildqualitaet=request.form.get('bildqualitaet', type=int),
            laenge_min=request.form.get('laenge_min', type=int),
            bewertung=request.form.get('bewertung', type=int),
            bereich_id=bereich_id,
        )
        ds.kategorien = Kategorie.query.filter(Kategorie.id.in_(kat_ids)).all()
        db.session.add(ds)
        db.session.commit()
        flash('Datensatz gespeichert.', 'success')
        return redirect(url_for('dashboard', bereich=bereich_id or ''))

    # Kategorien für vorgewählten Bereich
    kategorien = []
    if vorgewaehlter_bereich:
        kategorien = Kategorie.query.filter_by(bereich_id=vorgewaehlter_bereich)\
                                    .order_by(Kategorie.name).all()

    return render_template(
        'form.html',
        ds=None,
        bereiche=bereiche,
        kategorien=kategorien,
        vorgewaehlter_bereich=vorgewaehlter_bereich,
    )


# ─────────────────────────────────────────────
# Datensatz: Bearbeiten
# ─────────────────────────────────────────────

@app.route('/datensatz/<int:ds_id>', methods=['GET', 'POST'])
@login_required
def detail(ds_id):
    ds = Datensatz.query.get_or_404(ds_id)
    bereiche = Bereich.query.order_by(Bereich.reihenfolge, Bereich.name).all()

    if request.method == 'POST':
        bereich_id = request.form.get('bereich_id', type=int) or None
        kat_ids = request.form.getlist('kategorien', type=int)
        ds.url = request.form.get('url', '').strip()
        ds.provider = request.form.get('provider', '').strip()
        ds.thumbnail_url = request.form.get('thumbnail_url', '').strip()
        ds.titel = request.form.get('titel', '').strip()
        ds.bildqualitaet = request.form.get('bildqualitaet', type=int)
        ds.laenge_min = request.form.get('laenge_min', type=int)
        ds.bewertung = request.form.get('bewertung', type=int)
        ds.bereich_id = bereich_id
        ds.kategorien = Kategorie.query.filter(Kategorie.id.in_(kat_ids)).all()
        db.session.commit()
        flash('Datensatz aktualisiert.', 'success')
        return redirect(url_for('dashboard', bereich=bereich_id or ''))

    # Kategorien für den Bereich des Datensatzes
    kategorien = []
    if ds.bereich_id:
        kategorien = Kategorie.query.filter_by(bereich_id=ds.bereich_id)\
                                    .order_by(Kategorie.name).all()

    return render_template(
        'form.html',
        ds=ds,
        bereiche=bereiche,
        kategorien=kategorien,
        vorgewaehlter_bereich=ds.bereich_id,
    )


# ─────────────────────────────────────────────
# Datensatz: Löschen
# ─────────────────────────────────────────────

@app.route('/datensatz/<int:ds_id>/loeschen', methods=['POST'])
@login_required
def loeschen(ds_id):
    ds = Datensatz.query.get_or_404(ds_id)
    bid = ds.bereich_id
    db.session.delete(ds)
    db.session.commit()
    flash('Datensatz gelöscht.', 'info')
    return redirect(url_for('dashboard', bereich=bid or ''))


# ─────────────────────────────────────────────
# Datensatz: Go (Aufruf-Zähler + URL zurückgeben)
# ─────────────────────────────────────────────

@app.route('/datensatz/<int:ds_id>/go', methods=['POST'])
@login_required
def go(ds_id):
    ds = Datensatz.query.get_or_404(ds_id)
    ds.aufrufe = (ds.aufrufe or 0) + 1
    db.session.commit()
    return jsonify({'aufrufe': ds.aufrufe, 'url': ds.url})


# ─────────────────────────────────────────────
# Einstellungen
# ─────────────────────────────────────────────

@app.route('/einstellungen', methods=['GET', 'POST'])
@login_required
def einstellungen():
    bereiche = Bereich.query.order_by(Bereich.reihenfolge, Bereich.name).all()

    if request.method == 'POST':
        aktion = request.form.get('aktion')

        # Bereich anlegen
        if aktion == 'bereich_neu':
            name = request.form.get('bereich_name', '').strip()
            if name:
                b = Bereich(name=name, reihenfolge=len(bereiche))
                db.session.add(b)
                db.session.commit()
                flash(f'Bereich „{name}" angelegt.', 'success')

        # Bereich umbenennen
        elif aktion == 'bereich_umbenennen':
            bid = request.form.get('bereich_id', type=int)
            name = request.form.get('bereich_name_neu', '').strip()
            b = Bereich.query.get(bid)
            if b and name:
                b.name = name
                db.session.commit()
                flash(f'Bereich umbenannt in „{name}".', 'success')

        # Bereich löschen
        elif aktion == 'bereich_loeschen':
            bid = request.form.get('bereich_id', type=int)
            b = Bereich.query.get(bid)
            if b:
                name = b.name
                db.session.delete(b)
                db.session.commit()
                flash(f'Bereich „{name}" und alle zugehörigen Kategorien gelöscht.', 'info')

        # Kategorie anlegen (immer mit Bereich)
        elif aktion == 'kat_neu':
            name = request.form.get('kat_name', '').strip()
            bid = request.form.get('kat_bereich_id', type=int)
            if name and bid:
                k = Kategorie(name=name, bereich_id=bid)
                db.session.add(k)
                db.session.commit()
                flash(f'Kategorie „{name}" angelegt.', 'success')

        # Kategorie löschen
        elif aktion == 'kat_loeschen':
            kid = request.form.get('kat_id', type=int)
            k = Kategorie.query.get(kid)
            if k:
                name = k.name
                db.session.delete(k)
                db.session.commit()
                flash(f'Kategorie „{name}" gelöscht.', 'info')

        # Passwort ändern
        elif aktion == 'pw_aendern':
            pw_neu = request.form.get('pw_neu', '')
            pw_bestaetigung = request.form.get('pw_bestaetigung', '')
            if pw_neu and pw_neu == pw_bestaetigung:
                save_password_hash(generate_password_hash(pw_neu))
                flash('Passwort geändert.', 'success')
            else:
                flash('Passwörter stimmen nicht überein.', 'danger')

        return redirect(url_for('einstellungen'))

    return render_template('settings.html', bereiche=bereiche)


# ─────────────────────────────────────────────
# DB-Migrationen (für bestehende Datenbanken)
# ─────────────────────────────────────────────

def run_migrations():
    """Fügt fehlende Spalten zu bestehenden Tabellen hinzu."""
    with db.engine.connect() as conn:
        from sqlalchemy import text
        try:
            conn.execute(text(
                'ALTER TABLE kategorien ADD COLUMN bereich_id INTEGER'
            ))
            conn.commit()
        except Exception:
            pass  # Spalte existiert bereits


# ─────────────────────────────────────────────
# App-Start
# ─────────────────────────────────────────────

with app.app_context():
    db.create_all()
    run_migrations()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
