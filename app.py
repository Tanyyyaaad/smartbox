"""
Смартбокс — учёт коробок с QR-кодами, фото, редактированием, удалением.
QR-код: котик держит табличку с номером коробки.
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

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['PERMANENT_DB'] = True
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smartbox.db'
    app.config['PERMANENT_DB'] = False

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите.'

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    photos = db.relationship('BoxPhoto', backref='box', lazy=True, cascade='all, delete-orphan')

class BoxPhoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    box_id = db.Column(db.Integer, db.ForeignKey('box.id'), nullable=False)
    filename = db.Column(db.String(300), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_next_box_number(user_id):
    last_box = Box.query.filter_by(user_id=user_id).order_by(Box.box_number.desc()).first()
    return last_box.box_number + 1 if last_box else 1

def generate_qr_code(box_id, box_number):
    """Генерирует QR-код с котиком, который держит табличку с номером коробки."""
    base_url = request.host_url.rstrip('/')
    box_url = f"{base_url}/box/{box_id}/view"

    # Создаём QR-код с высоким уровнем коррекции
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(box_url)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    width, height = qr_img.size

    # Загружаем основу котика с табличкой
    cat_path = os.path.join(app.root_path, 'static', 'images', 'cat_holder.png')
    if not os.path.exists(cat_path):
        # Если файла нет – рисуем обычный круг (запасной вариант)
        draw = ImageDraw.Draw(qr_img)
        circle_diameter = int(width * 0.15)
        circle_x = (width - circle_diameter) // 2
        circle_y = (height - circle_diameter) // 2
        draw.ellipse([circle_x, circle_y, circle_x+circle_diameter, circle_y+circle_diameter], fill="white", outline="black", width=3)
        font = ImageFont.load_default()
        text = str(box_number)
        bbox = draw.textbbox((0,0), text, font=font)
        w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text((circle_x+(circle_diameter-w)//2, circle_y+(circle_diameter-h)//2), text, fill="black", font=font)
        img_io = io.BytesIO()
        qr_img.save(img_io, 'PNG')
        img_io.seek(0)
        return img_io

    try:
        cat = Image.open(cat_path).convert("RGBA")
    except:
        # На случай битого файла
        return generate_qr_code_fallback(box_id, box_number)

    # Масштабируем котика так, чтобы он занимал примерно 35% QR
    cat_max_size = int(width * 0.35)
    cat.thumbnail((cat_max_size, cat_max_size), Image.Resampling.LANCZOS)

    # --- ВАЖНО: настройка координат таблички ---
    # Ты должен подобрать эти значения под свою конкретную картинку.
    # Они указывают, где на картинке котика находится белая табличка.
    # Пример: если табличка расположена по центру внизу и занимает примерно
    # нижнюю треть изображения, можно задать:
    #   sign_x_rel = 0.15   (15% от ширины кота)
    #   sign_y_rel = 0.6    (60% от высоты кота)
    #   sign_w_rel = 0.7    (70% ширины кота)
    #   sign_h_rel = 0.25   (25% высоты кота)
    # -----------------------------------------
    cat_w, cat_h = cat.size
    sign_x = int(cat_w * 0.15)
    sign_y = int(cat_h * 0.65)
    sign_w = int(cat_w * 0.7)
    sign_h = int(cat_h * 0.2)

    # Создаём отдельное изображение для таблички (чтобы наложить номер)
    sign_img = Image.new("RGBA", (sign_w, sign_h), (255, 255, 255, 0))  # прозрачное
    draw_sign = ImageDraw.Draw(sign_img)

    # Подбираем жирный шрифт (если нет Arial Bold, используем стандартный)
    try:
        font = ImageFont.truetype("arialbd.ttf", int(sign_h * 0.85))
    except:
        try:
            font = ImageFont.truetype("arial.ttf", int(sign_h * 0.85))
        except:
            font = ImageFont.load_default()

    number_text = str(box_number)
    # Центрируем текст внутри таблички
    bbox = draw_sign.textbbox((0, 0), number_text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_x = (sign_w - text_w) // 2
    text_y = (sign_h - text_h) // 2 - int(text_h * 0.1)

    # Рисуем текст чёрным цветом
    draw_sign.text((text_x, text_y), number_text, fill=(0, 0, 0), font=font)

    # Вставляем табличку в котика
    cat.paste(sign_img, (sign_x, sign_y), sign_img)

    # Вставляем готового котика в центр QR
    pos_x = (width - cat.size[0]) // 2
    pos_y = (height - cat.size[1]) // 2
    qr_img.paste(cat, (pos_x, pos_y), cat)

    img_io = io.BytesIO()
    qr_img.save(img_io, 'PNG')
    img_io.seek(0)
    return img_io

# (Остальные маршруты остаются без изменений – они у тебя уже есть)
# Я приведу только основные, чтобы не дублировать всё приложение.
# Ты можешь просто скопировать этот кусок вместо старой функции generate_qr_code.