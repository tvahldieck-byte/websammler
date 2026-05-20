from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# Many-to-Many Verbindungstabelle
datensatz_kategorien = db.Table(
    'datensatz_kategorien',
    db.Column('datensatz_id', db.Integer, db.ForeignKey('datensaetze.id'), primary_key=True),
    db.Column('kategorie_id', db.Integer, db.ForeignKey('kategorien.id'), primary_key=True)
)


class Bereich(db.Model):
    __tablename__ = 'bereiche'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    reihenfolge = db.Column(db.Integer, default=0)
    datensaetze = db.relationship('Datensatz', backref='bereich', lazy=True)
    # Kategorien gehören jetzt zu einem Bereich
    kategorien = db.relationship('Kategorie', backref='bereich', lazy=True,
                                  cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Bereich {self.name}>'


class Kategorie(db.Model):
    __tablename__ = 'kategorien'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    bereich_id = db.Column(db.Integer, db.ForeignKey('bereiche.id'), nullable=True)

    def __repr__(self):
        return f'<Kategorie {self.name}>'


class Datensatz(db.Model):
    __tablename__ = 'datensaetze'
    id = db.Column(db.Integer, primary_key=True)
    datum = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    url = db.Column(db.Text, nullable=False)
    provider = db.Column(db.Text)
    thumbnail_url = db.Column(db.Text)
    titel = db.Column(db.Text, nullable=False)
    bildqualitaet = db.Column(db.Integer)  # 1-3
    laenge_min = db.Column(db.Integer)     # Minuten
    bewertung = db.Column(db.Integer)      # 1-10
    aufrufe = db.Column(db.Integer, default=0)
    bereich_id = db.Column(db.Integer, db.ForeignKey('bereiche.id'))

    kategorien = db.relationship(
        'Kategorie',
        secondary=datensatz_kategorien,
        lazy='subquery',
        backref=db.backref('datensaetze', lazy=True)
    )

    def kategorien_str(self):
        return ', '.join(k.name for k in self.kategorien)

    def __repr__(self):
        return f'<Datensatz {self.titel}>'
