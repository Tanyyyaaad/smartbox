from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import qrcode
from io import BytesIO
from PIL import ImageDraw, ImageFont
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'секретный-ключ'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smartbox.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    boxes = db.relationship('Box', backref='owner', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Box(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    color = db.Column(db.String(50), default='#4CAF50')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    box_number = db.Column(db.Integer, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def get_next_box_number(user_id):
    last_box = Box.query.filter_by(user_id=user_id).order_by(Box.box_number.desc()).first()
    return (last_box.box_number + 1) if last_box else 1

def generate_qr_with_number(box_number, username, box_id):
    url = url_for('view_box', box_id=box_id, _external=True)
    qr = qrcode.QRCode(version=3, box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except:
        font = ImageFont.load_default()
    text = f"{box_number}\n{username}"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    img_width, img_height = img.size
    x = (img_width - text_width) // 2
    y = (img_height - text_height) // 2
    draw.text((x, y), text, fill="black", font=font)
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Имя пользователя уже занято')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email уже зарегистрирован')
            return redirect(url_for('register'))
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Регистрация успешна, войдите')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Неверное имя или пароль')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    boxes = Box.query.filter_by(user_id=current_user.id).order_by(Box.created_at.desc()).all()
    return render_template('dashboard.html', boxes=boxes)

@app.route('/create_box', methods=['GET', 'POST'])
@login_required
def create_box():
    if request.method == 'POST':
        name = request.form['name']
        content = request.form['content']
        color = request.form.get('color', '#4CAF50')
        box_number = get_next_box_number(current_user.id)
        box = Box(user_id=current_user.id, name=name, content=content, color=color, box_number=box_number)
        db.session.add(box)
        db.session.commit()
        qr_buffer = generate_qr_with_number(box_number, current_user.username, box.id)
        return send_file(qr_buffer, mimetype='image/png', as_attachment=True, download_name=f'box_{box_number}.png')
    return render_template('create_box.html')

@app.route('/box/<int:box_id>')
def view_box(box_id):
    box = Box.query.get_or_404(box_id)
    return render_template('box_detail.html', box=box)

@app.route('/search', methods=['GET'])
@login_required
def search():
    query = request.args.get('q', '')
    if query:
        results = Box.query.filter(Box.user_id == current_user.id, Box.content.ilike(f'%{query}%')).all()
    else:
        results = []
    return render_template('search_results.html', query=query, results=results)

@app.route('/download_qr/<int:box_id>')
@login_required
def download_qr(box_id):
    box = Box.query.get_or_404(box_id)
    if box.user_id != current_user.id:
        flash('Не ваша коробка')
        return redirect(url_for('dashboard'))
    qr_buffer = generate_qr_with_number(box.box_number, current_user.username, box.id)
    return send_file(qr_buffer, mimetype='image/png', as_attachment=True, download_name=f'box_{box.box_number}.png')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)