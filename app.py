"""
Сайт «Смартбокс» — учёт коробок с QR‑кодами.
Автор: для стартапа @Исакова Татьяна.
"""

import os
import io
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    send_file, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode
from PIL import Image, ImageDraw, ImageFont

# ---------- НАСТРОЙКИ ПРИЛОЖЕНИЯ ----------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'  # Замените на что‑то сложное!
# Путь к базе данных SQLite (файл появится в папке instance)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smartbox.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'      # куда перенаправлять неавторизованных
login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице.'

# ---------- МОДЕЛИ БАЗЫ ДАННЫХ ----------
class User(UserMixin, db.Model):
    """Пользователь сайта."""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), nullable=False)       # Никнейм
    password_hash = db.Column(db.String(200), nullable=False)
    boxes = db.relationship('Box', backref='owner', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Box(db.Model):
    """Коробка, принадлежащая пользователю."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    box_number = db.Column(db.Integer, nullable=False)        # Номер коробки у пользователя
    name = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    color = db.Column(db.String(7), default='#e0e0e0')        # HEX-код цвета
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
def get_next_box_number(user_id):
    """Возвращает следующий порядковый номер коробки для данного пользователя."""
    last_box = Box.query.filter_by(user_id=user_id).order_by(Box.box_number.desc()).first()
    if last_box:
        return last_box.box_number + 1
    return 1

def generate_qr_code(box_id, box_number, username):
    """
    Генерирует QR‑код с ссылкой на публичную страницу коробки.
    В центр QR‑кода вписываются две строки: номер коробки и имя пользователя.
    Возвращает объект BytesIO с PNG-изображением.
    """
    # Публичная ссылка (замените домен при выкладке на Render!)
    # Пока на локальной машине будет работать через localhost.
    # На Render будет использоваться реальный домен, его можно подставлять автоматически.
    base_url = request.host_url.rstrip('/')
    box_url = f"{base_url}/box/{box_id}/view"

    # 1. Создаём базовый QR-код
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # высокий уровень коррекции
        box_size=10,
        border=4,
    )
    qr.add_data(box_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    width, height = img.size

    # 2. Рисуем текст в центре
    draw = ImageDraw.Draw(img)

    # Пытаемся загрузить системный шрифт. Если не получится – используем стандартный.
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except IOError:
        font = ImageFont.load_default()

    text_line1 = str(box_number)
    text_line2 = username

    # Определяем размеры текста для центрирования
    # В Pillow есть textbbox (или устаревший textsize). Используем textbbox.
    bbox1 = draw.textbbox((0, 0), text_line1, font=font)
    w1 = bbox1[2] - bbox1[0]
    h1 = bbox1[3] - bbox1[1]

    bbox2 = draw.textbbox((0, 0), text_line2, font=font)
    w2 = bbox2[2] - bbox2[0]
    h2 = bbox2[3] - bbox2[1]

    # Позиция для двух строк (центр изображения)
    total_height = h1 + h2 + 5  # 5 пикселей между строками
    y_start = (height - total_height) // 2

    x1 = (width - w1) // 2
    y1 = y_start
    draw.text((x1, y1), text_line1, fill="black", font=font)

    x2 = (width - w2) // 2
    y2 = y1 + h1 + 5
    draw.text((x2, y2), text_line2, fill="black", font=font)

    # 3. Сохраняем в памяти
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return img_io

# ---------- МАРШРУТЫ (СТРАНИЦЫ) ----------
@app.route('/')
def index():
    """Главная страница: если авторизован — в личный кабинет, иначе на вход."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Регистрация нового пользователя."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        # Простейшие проверки
        if not email or not username or not password:
            flash('Все поля обязательны для заполнения.', 'danger')
            return redirect(url_for('register'))
        if password != password2:
            flash('Пароли не совпадают.', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Пользователь с таким email уже существует.', 'danger')
            return redirect(url_for('register'))

        user = User(email=email, username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Регистрация прошла успешно! Теперь войдите.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Вход в систему."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            flash('Добро пожаловать!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Неверный email или пароль.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Выход из учётной записи."""
    logout_user()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Личный кабинет со списком коробок."""
    boxes = Box.query.filter_by(user_id=current_user.id).order_by(Box.box_number).all()
    return render_template('dashboard.html', boxes=boxes)

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_box():
    """
    Создание новой коробки.
    После успешного создания сразу отдаётся QR‑код для скачивания.
    """
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        content = request.form.get('content', '').strip()
        color = request.form.get('color', '#e0e0e0')

        if not name or not content:
            flash('Название и содержимое обязательны.', 'danger')
            return redirect(url_for('create_box'))

        # Получаем следующий номер
        next_num = get_next_box_number(current_user.id)

        box = Box(
            user_id=current_user.id,
            box_number=next_num,
            name=name,
            content=content,
            color=color
        )
        db.session.add(box)
        db.session.commit()

        # Генерируем QR‑код и отдаём как файл для скачивания
        qr_image = generate_qr_code(box.id, box.box_number, current_user.username)
        return send_file(
            qr_image,
            mimetype='image/png',
            as_attachment=True,
            download_name=f'qr_box_{box.box_number}_{current_user.username}.png'
        )

    return render_template('create_box.html')

@app.route('/box/<int:box_id>/view')
def box_view(box_id):
    """Публичная страница просмотра коробки (доступна по QR‑коду)."""
    box = Box.query.get_or_404(box_id)
    owner = User.query.get(box.user_id)
    return render_template('box_view.html', box=box, owner=owner)

@app.route('/box/<int:box_id>/qrcode')
@login_required
def download_qr(box_id):
    """
    Повторное скачивание QR‑кода (только для владельца коробки).
    """
    box = Box.query.get_or_404(box_id)
    if box.user_id != current_user.id:
        abort(403)  # запрещено

    qr_image = generate_qr_code(box.id, box.box_number, current_user.username)
    return send_file(
        qr_image,
        mimetype='image/png',
        as_attachment=True,
        download_name=f'qr_box_{box.box_number}_{current_user.username}.png'
    )

@app.route('/search', methods=['GET'])
@login_required
def search():
    """Поиск по содержимому коробок пользователя."""
    query = request.args.get('q', '').strip()
    if not query:
        flash('Введите слово для поиска.', 'warning')
        return redirect(url_for('dashboard'))

    # Ищем в содержимом (можно также добавить поиск по названию)
    results = Box.query.filter(
        Box.user_id == current_user.id,
        Box.content.contains(query) | Box.name.contains(query)
    ).order_by(Box.box_number).all()

    return render_template('search_results.html', results=results, query=query)

# ---------- ОБРАБОТЧИКИ ОШИБОК ----------
@app.errorhandler(404)
def not_found_error(error):
    return render_template('base.html', error='Страница не найдена'), 404

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('base.html', error='Доступ запрещён'), 403

# ---------- ТОЧКА ВХОДА ----------
if __name__ == '__main__':
    # Создаём папку instance и базу данных, если их нет
    with app.app_context():
        db.create_all()
    # Запуск сервера для разработки
    app.run(debug=True, host='0.0.0.0', port=5000)