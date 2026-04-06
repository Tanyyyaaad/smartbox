from flask import Flask, render_template, request, redirect, url_for, send_file
import qrcode
from io import BytesIO
import uuid

app = Flask(__name__)
boxes = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create', methods=['GET', 'POST'])
def create():
    if request.method == 'POST':
        name = request.form['name']
        content = request.form['content']
        box_id = str(uuid.uuid4())[:8]
        boxes[box_id] = {'name': name, 'content': content}
        qr_url = url_for('view_box', box_id=box_id, _external=True)
        img = qrcode.make(qr_url)
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return send_file(buffer, mimetype='image/png', as_attachment=True, download_name=f'{box_id}.png')
    return render_template('create.html')

@app.route('/box/<box_id>')
def view_box(box_id):
    box = boxes.get(box_id)
    if not box:
        return "Коробка не найдена", 404
    return render_template('box.html', name=box['name'], content=box['content'], box_id=box_id)

if __name__ == '__main__':
    app.run(debug=True)