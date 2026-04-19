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
        # Получаем следующий номер
        box_number = get_next_box_number(current_user.id)
        # Создаем коробку
        box = Box(user_id=current_user.id, name=name, content=content, color=color, box_number=box_number)
        db.session.add(box)
        db.session.commit()
        # Генерируем QR с номером и ником
        qr_buffer = generate_qr_with_number(box_number, current_user.username, box.id)
        return send_file(qr_buffer, mimetype='image/png', as_attachment=True, download_name=f'box_{box_number}.png')
    return render_template('create_box.html')

@app.route('/box/<int:box_id>')
def view_box(box_id):
    box = Box.query.get_or_404(box_id)
    # Можно смотреть даже без логина, но только содержимое
    return render_template('box_detail.html', box=box)

@app.route('/search', methods=['GET'])
@login_required
def search():
    query = request.args.get('q', '')
    if query:
        # Ищем по содержимому коробок текущего пользователя (без учета регистра)
        results = Box.query.filter(Box.user_id == current_user.id, Box.content.ilike(f'%{query}%')).all()
    else:
        results = []
    return render_template('search_results.html', query=query, results=results)

# ---------- Запуск ----------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)