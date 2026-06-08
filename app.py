def generate_qr_code(box_id, box_number):
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

    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    width, height = qr_img.size

    # Пытаемся загрузить котика
    cat_path = os.path.join(app.root_path, 'static', 'images', 'cat_holder.png')
    if not os.path.exists(cat_path):
        # Запасной вариант – белый круг с номером
        draw = ImageDraw.Draw(qr_img)
        circle_d = int(width * 0.15)
        cx = (width - circle_d) // 2
        cy = (height - circle_d) // 2
        draw.ellipse([cx, cy, cx+circle_d, cy+circle_d], fill="white", outline="black", width=3)
        try:
            font = ImageFont.truetype("arial.ttf", int(circle_d*0.9))
        except:
            font = ImageFont.load_default()
        text = str(box_number)
        bbox = draw.textbbox((0,0), text, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text((cx+(circle_d-tw)//2, cy+(circle_d-th)//2), text, fill="black", font=font)
        img_io = io.BytesIO()
        qr_img.save(img_io, 'PNG')
        img_io.seek(0)
        return img_io

    try:
        cat = Image.open(cat_path).convert("RGBA")
    except:
        # Если файл битый – fallback
        return generate_qr_code_fallback(box_id, box_number)

    # Масштабируем котика до 35% ширины QR, сохраняя пропорции (они у нас 1:1)
    cat_max_size = int(width * 0.35)
    cat.thumbnail((cat_max_size, cat_max_size), Image.Resampling.LANCZOS)
    cat_w, cat_h = cat.size

    # --- КООРДИНАТЫ ТАБЛИЧКИ ДЛЯ КВАДРАТНОЙ КАРТИНКИ ---
    # Эти числа подходят для стандартного расположения:
    # табличка находится в нижней центральной части,
    # её ширина ≈ 60% ширины кота, высота ≈ 25% высоты,
    # левый верхний угол ≈ (20%, 62%).
    # Если твоя картинка немного отличается, просто подкорректируй эти проценты.
    sign_x = int(cat_w * 0.20)
    sign_y = int(cat_h * 0.62)
    sign_w = int(cat_w * 0.60)
    sign_h = int(cat_h * 0.25)
    # ------------------------------------------------

    # Создаём чистый слой для номера
    sign_img = Image.new("RGBA", (sign_w, sign_h), (255, 255, 255, 0))
    draw_sign = ImageDraw.Draw(sign_img)

    # Жирный шрифт (почти на всю высоту таблички)
    try:
        font = ImageFont.truetype("arialbd.ttf", int(sign_h * 0.85))
    except:
        try:
            font = ImageFont.truetype("arial.ttf", int(sign_h * 0.85))
        except:
            font = ImageFont.load_default()

    number_text = str(box_number)
    # Центрируем надпись
    bbox = draw_sign.textbbox((0, 0), number_text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_x = (sign_w - text_w) // 2
    text_y = (sign_h - text_h) // 2 - int(text_h * 0.1)

    draw_sign.text((text_x, text_y), number_text, fill=(0, 0, 0), font=font)

    # Накладываем номер на котика
    cat.paste(sign_img, (sign_x, sign_y), sign_img)

    # Вставляем котика в центр QR
    pos_x = (width - cat.size[0]) // 2
    pos_y = (height - cat.size[1]) // 2
    qr_img.paste(cat, (pos_x, pos_y), cat)

    img_io = io.BytesIO()
    qr_img.save(img_io, 'PNG')
    img_io.seek(0)
    return img_io