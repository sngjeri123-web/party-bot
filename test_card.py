"""Тестовый скрипт — генерирует пример карточки и открывает её."""
import asyncio
import io
import os
import httpx
from PIL import Image, ImageDraw, ImageFont

# Импортируем функции из бота
from bot import download_flag, crop_circle, generate_card, _get_font


async def create_test_photo() -> bytes:
    """Скачать тестовое фото (случайное лицо) или создать заглушку."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get("https://picsum.photos/400/400", timeout=10)
            resp.raise_for_status()
            return resp.content
    except Exception:
        # Заглушка — цветной круг с текстом
        img = Image.new("RGB", (400, 400), (100, 150, 200))
        draw = ImageDraw.Draw(img)
        draw.ellipse((50, 50, 350, 350), fill=(200, 100, 150))
        font = _get_font(40)
        draw.text((120, 180), "ФОТО", fill="white", font=font)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


async def main():
    print("📸 Скачиваю тестовое фото...")
    test_photo = await create_test_photo()

    print("🎨 Генерирую карточку: Лиза и Стёпа — Грузинская кухня...")
    card_bytes = await generate_card(
        photo_bytes=test_photo,
        names="Лиза и Стёпа",
        cuisine_name="Грузинская",
        flag_emoji="🇬🇪",
        description="Хачапури, хинкали, шашлык, сациви",
        country_code="ge",
    )

    # Сохраняем
    out_path = os.path.join(os.path.dirname(__file__), "test_card_with_photo.png")
    with open(out_path, "wb") as f:
        f.write(card_bytes)
    print(f"✅ Сохранено: {out_path}")

    print("🎨 Генерирую карточку БЕЗ фото: Артём — Японская кухня...")
    card_no_photo = await generate_card(
        photo_bytes=None,
        names="Артём",
        cuisine_name="Японская",
        flag_emoji="🇯🇵",
        description="Суши, рамен, темпура, мисо-суп",
        country_code="jp",
    )

    out_path2 = os.path.join(os.path.dirname(__file__), "test_card_no_photo.png")
    with open(out_path2, "wb") as f:
        f.write(card_no_photo)
    print(f"✅ Сохранено: {out_path2}")

    # Открываем для просмотра
    os.system(f"open '{out_path}'")
    os.system(f"open '{out_path2}'")
    print("🎉 Готово! Смотри картинки.")


if __name__ == "__main__":
    asyncio.run(main())
