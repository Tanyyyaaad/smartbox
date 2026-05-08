"""
Смартбокс — учёт коробок с QR-кодами, фото, редактированием и удалением.
QR-код содержит ссылку на коробку и крупный номер в белом круге по центру.
"""

import io
import os
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    send_file, abort, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode
from PIL import Image, ImageDraw, ImageFont

# ---------- НАСТРОЙКИ ----------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-me-to-some-random-string'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Папка для загруженных фото
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

# База данных: если есть DATABASE_URL (PostgreSQL), берём её, иначе SQLite
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['PERMANENT_DB'] = True
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smartbox.db'
    app.config['PERMANENT_DB'] = False

# Создаём папку uploads, если её нет
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите.'

# ---------- МОДЕЛИ ----------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    boxes = db.relationship('Box', backref='owner', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Box(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    box_number = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    color = db.Column(db.String(7), default='#e0e0e0')
    photo = db.Column(db.String(300), nullable=True)   # имя файла фото
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Создаём таблицы при старте
with app.app_context():
    db.create_all()

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_next_box_number(user_id):
    last_box = Box.query.filter_by(user_id=user_id).order_by(Box.box_number.desc()).first()
    return last_box.box_number + 1 if last_box else 1

def generate_qr_code(box_id, box_number):
    """
    Генерирует QR-код со ссылкой на коробку.
    В центре — крупный номер, обведённый белым кругом с чёрной рамкой.
    """
    base_url = request.host_url.rstrip('/')
    box_url = f"{base_url}/box/{box_id}/view"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(box_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    draw = ImageDraw.Draw(img)

    # Размер изображения
    width, height = img.size

    # Круг в центре
    circle_diameter = int(width * 0.28)          # занимает 28% ширины QR
    circle_radius = circle_diameter // 2
    circle_x = (width - circle_diameter) // 2
    circle_y = (height - circle_diameter) // 2

    # Рисуем белый круг с чёрной границей
    draw.ellipse(
        [circle_x, circle_y, circle_x + circle_diameter, circle_y + circle_diameter],
        fill="white",
        outline="black",
        width=5
    )

    # Шрифт для цифры
    try:
        font = ImageFont.truetype("arial.ttf", circle_diameter // 2)   # крупный шрифт
    except IOError:
        font = ImageFont.load_default()

    text = str(box_number)

    # Центрируем текст внутри круга
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = circle_x + (circle_diameter - w) // 2
    y = circle_y + (circle_diameter - h) // 2 - int(h * 0.1)

    draw.text((x, y), text, fill="black", font=font)

    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return img_io

def save_photo(file):
    """Сохраняет загруженный файл и возвращает имя файла."""
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Добавляем микросекунды, чтобы имена не повторялись
        unique_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
        return unique_name
    return None

# Контекст-процессор для демо-баннера
@app.context_processor
def inject_db_status():
    return dict(permanent_db=app.config.get('PERMANENT_DB', False))

# ---------- МАРШРУТЫ ----------
@app.route('/')
def index():
    return redirect(url_for('dashboard') if current_user.is_authenticated else url_for('login'))

@app.route('/register', methods=['GET','POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email','').strip()
        username = request.form.get('username','').strip()
        pwd = request.form.get('password','')
        pwd2 = request.form.get('password2','')
        if not email or not username or not pwd:
            flash('Все поля обязательны', 'danger')
        elif pwd != pwd2:
            flash('Пароли не совпадают', 'danger')
        elif User.query.filter_by(email=email).first():
            flash('Email уже занят', 'danger')
        else:
            user = User(email=email, username=username)
            user.set_password(pwd)
            db.session.add(user)
            db.session.commit()
            flash('Регистрация успешна! Войдите.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email','').strip()
        pwd = request.form.get('password','')
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(pwd):
            login_user(user, remember=True)
            flash('Добро пожаловать!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Неверный email или пароль', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    boxes = Box.query.filter_by(user_id=current_user.id).order_by(Box.box_number).all()
    return render_template('dashboard.html', boxes=boxes)

@app.route('/create', methods=['GET','POST'])
@login_required
def create_box():
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        content = request.form.get('content','').strip()
        color = request.form.get('color','#e0e0e0')
        if not name or not content:
            flash('Название и содержимое обязательны', 'danger')
            return redirect(url_for('create_box'))

        # Обработка фото
        photo_file = request.files.get('photo')
        photo_filename = save_photo(photo_file) if photo_file else None

        next_num = get_next_box_number(current_user.id)
        box = Box(
            user_id=current_user.id,
            box_number=next_num,
            name=name,
            content=content,
            color=color,
            photo=photo_filename
        )
        db.session.add(box)
        db.session.commit()
        qr_img = generate_qr_code(box.id, box.box_number)
        return send_file(qr_img, mimetype='image/png', as_attachment=True,
                         download_name=f'qr_box_{box.box_number}.png')
    return render_template('create_box.html')

@app.route('/edit/<int:box_id>', methods=['GET','POST'])
@login_required
def edit_box(box_id):
    box = Box.query.get_or_404(box_id)
    if box.user_id != current_user.id:
        abort(403)

    if request.method == 'POST':
        box.name = request.form.get('name', '').strip()
        box.content = request.form.get('content', '').strip()
        box.color = request.form.get('color', '#e0e0e0')

        if not box.name or not box.content:
            flash('Название и содержимое обязательны', 'danger')
            return redirect(url_for('edit_box', box_id=box.id))

        # Обработка нового фото (если загрузили)
        photo_file = request.files.get('photo')
        if photo_file and photo_file.filename:
            # Удаляем старое фото, если было
            if box.photo:
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], box.photo)
                if os.path.exists(old_path):
                    os.remove(old_path)
            new_photo = save_photo(photo_file)
            if new_photo:
                box.photo = new_photo

        db.session.commit()
        flash('Коробка обновлена!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('edit_box.html', box=box)

@app.route('/delete/<int:box_id>', methods=['POST'])
@login_required
def delete_box(box_id):
    box = Box.query.get_or_404(box_id)
    if box.user_id != current_user.id:
        abort(403)

    # Удаляем фото с диска, если есть
    if box.photo:
        photo_path = os.path.join(app.config['UPLOAD_FOLDER'], box.photo)
        if os.path.exists(photo_path):
            os.remove(photo_path)

    db.session.delete(box)
    db.session.commit()
    flash('Коробка удалена.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/box/<int:box_id>/view')
def box_view(box_id):
    box = Box.query.get_or_404(box_id)
    owner = User.query.get(box.user_id)
    if not owner:
        owner = type('obj', (object,), {'username': 'Неизвестный'})()
    return render_template('box_view.html', box=box, owner=owner)

@app.route('/box/<int:box_id>/qrcode')
@login_required
def download_qr(box_id):
    box = Box.query.get_or_404(box_id)
    if box.user_id != current_user.id:
        abort(403)
    qr_img = generate_qr_code(box.id, box.box_number)
    return send_file(qr_img, mimetype='image/png', as_attachment=True,
                     download_name=f'qr_box_{box.box_number}.png')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/search')
@login_required
def search():
    q = request.args.get('q','').strip()
    if not q:
        flash('Введите слово', 'warning')
        return redirect(url_for('dashboard'))
    results = Box.query.filter(Box.user_id==current_user.id,
                               (Box.content.contains(q)) | (Box.name.contains(q))).order_by(Box.box_number).all()
    return render_template('search_results.html', results=results, query=q)

@app.errorhandler(404)
def not_found(e):
    return render_template('base.html', error='Страница не найдена'), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template('base.html', error='Доступ запрещён'), 403

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)