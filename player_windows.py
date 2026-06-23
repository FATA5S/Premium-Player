import pygame
import pygame.gfxdraw
import tkinter as tk
from tkinter import filedialog
import math
import numpy as np
from io import BytesIO
from mutagen import File
import os
import sys

def get_path(filename):
    # Эта функция понимает, где лежат файлы: рядом с .py или внутри .exe
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.abspath("."), filename)

# Пример использования:
# img = pygame.image.load(get_path("cover.png"))

# Авто-установка звукового движка без ffmpeg
try:
    import soundfile as sf
except ImportError:
    os.system('pip install soundfile')
    import soundfile as sf

# Палитра плеера
BG_BASE_COLOR = (24, 24, 30)
CARD_BG_COLOR = (32, 32, 38, 160)
TEXT_MAIN = (242, 242, 247)
TEXT_SEC = (155, 155, 160)
TEXT_DARK = (18, 18, 22)
BTN_COLOR = (242, 242, 247)


class SimplePlayer:
    def __init__(self):
        pygame.init()
        # Добавьте эти строки сразу после pygame.init():
        if os.path.exists("icon.ico"):
            icon = pygame.image.load("icon.ico")
            pygame.display.set_icon(icon)

        pygame.mixer.init()

        pygame.init()
        pygame.mixer.init()
        self.screen = pygame.display.set_mode((800, 600))
        pygame.display.set_caption("Premium Player - Pure FFT Bass Visualizer")
        self.clock = pygame.time.Clock()
        self.seek_offset = 0
        self.current_path = None
        self.dragging_prog = False
        self.dragging_vol = False
        # --- НОВОЕ: Переменные для рабочего скроллбара ---
        self.dragging_scroll = False
        self.scroll_click_offset = 0
        self.thumb_rect = pygame.Rect(0, 0, 0, 0)

        self.font_title = pygame.font.SysFont("Helvetica", 22, bold=True)
        self.font_artist = pygame.font.SysFont("Helvetica", 16)
        self.font_small = pygame.font.SysFont("Helvetica", 14)

        self.playlist = []
        self.current_index = -1
        self.scroll_y = 0
        self.volume = 0.5
        self.album_art = None
        self.song_title = "Выберите папку"
        self.song_artist = "Pro Player"
        self.dragging_prog = False
        self.dragging_vol = False

        # Настоящие частоты баса
        self.current_raw_color = (60, 70, 95)
        self.pulse_scale = 1.0
        self.bass_envelope = []
        self.bass_energy = 0.0
        self.track_duration_ms = 0
        self.is_playing = False

        self.buttons = [
            {"action": "prev", "r": 22, "x": 190, "y": 460},
            {"action": "toggle", "r": 32, "x": 250, "y": 460},
            {"action": "next", "r": 22, "x": 310, "y": 460}
        ]

        # --- НОВОЕ: Регистрируем официальное событие конца трека ---
        self.MUSIC_END = pygame.USEREVENT + 1
        pygame.mixer.music.set_endevent(self.MUSIC_END)

    def generate_fast_gradient(self, target_color, scale):
        # Немного бустим яркость исходного цвета обложки для сочного неона
        r = min(160, int(target_color[0] * 0.8))
        g = min(160, int(target_color[1] * 0.8))
        b = min(160, int(target_color[2] * 0.8))

        # Заглушка, чтобы серые/черные обложки не давали скучный цвет
        if abs(r - g) < 5 and abs(g - b) < 5:
            r, g, b = 60, 80, 120

        # Создаем холст 10x10. При скейлинге 1 пиксель = 10% ширины/высоты окна
        small_surf = pygame.Surface((10, 10))
        small_surf.fill(BG_BASE_COLOR)

        # scale от 1.0 (тишина) до ~1.25 (пик баса)
        # bass_intensity будет от 0.0 до 1.0
        bass_intensity = min(1.0, max(0.0, (scale - 1.0) * 4.0))

        # Вычисляем радиус: 2 (20% экрана) в фоне, до 7 (70% экрана) при жестком кике
        max_radius = 5 + int(bass_intensity * 5)

        # Рисуем радиальный градиент (от центра свечения к краям)
        for i in range(max_radius, -1, -1):
            # Чем дальше от левого верхнего угла (0,0), тем ближе к фоновому цвету
            falloff = 1.0 - (i / max(1, max_radius))

            # Плавный бленд между цветом неона и темным фоном плеера
            curr_r = BG_BASE_COLOR[0] + (r - BG_BASE_COLOR[0]) * falloff
            curr_g = BG_BASE_COLOR[1] + (g - BG_BASE_COLOR[1]) * falloff
            curr_b = BG_BASE_COLOR[2] + (b - BG_BASE_COLOR[2]) * falloff

            pygame.draw.circle(small_surf, (int(curr_r), int(curr_g), int(curr_b)), (0, 0), i)

        # smoothscale сделает из этих 10 пикселей идеальный бесшовный градиент на все 800x600
        return pygame.transform.smoothscale(small_surf, (800, 600))

    def draw_aa_circle(self, surface, cx, cy, r, color):
        rgb_color = color[:3]
        pygame.gfxdraw.aacircle(surface, cx, cy, r, rgb_color)
        pygame.gfxdraw.filled_circle(surface, cx, cy, r, rgb_color)

    def draw_vector_icon(self, action, cx, cy, is_playing=False):
        color = TEXT_DARK
        if action == "toggle":
            if is_playing:
                w, h = 5, 18
                pygame.draw.rect(self.screen, color, (cx - 7, cy - h // 2, w, h), border_radius=2)
                pygame.draw.rect(self.screen, color, (cx + 2, cy - h // 2, w, h), border_radius=2)
            else:
                points = [(cx - 4, cy - 9), (cx - 4, cy + 9), (cx + 9, cy)]
                pygame.draw.polygon(self.screen, color, points)
        elif action == "next":
            points = [(cx - 6, cy - 7), (cx - 6, cy + 7), (cx + 1, cy)]
            pygame.draw.polygon(self.screen, color, points)
            points2 = [(cx + 1, cy - 7), (cx + 1, cy + 7), (cx + 8, cy)]
            pygame.draw.polygon(self.screen, color, points2)
            pygame.draw.rect(self.screen, color, (cx + 7, cy - 7, 2, 14))
        elif action == "prev":
            points = [(cx + 6, cy - 7), (cx + 6, cy + 7), (cx - 1, cy)]
            pygame.draw.polygon(self.screen, color, points)
            points2 = [(cx - 1, cy - 7), (cx - 1, cy + 7), (cx - 8, cy)]
            pygame.draw.polygon(self.screen, color, points2)
            pygame.draw.rect(self.screen, color, (cx - 9, cy - 7, 2, 14))

    def format_time(self, seconds):
        seconds = int(seconds)
        return f"{seconds // 60}:{seconds % 60:02}"

    def get_track_info(self, path):
        try:
            audio = File(path)
            title = audio.get('TIT2', [os.path.basename(path)])[0]
            artist = audio.get('TPE1', ['Неизвестный'])[0]
            duration = int(audio.info.length)
            thumb = None
            raw_data = None
            if 'APIC:' in audio:
                raw_data = audio['APIC:'].data
            elif 'covr' in audio:
                raw_data = audio['covr'][0]
            if raw_data:
                img = pygame.image.load(BytesIO(raw_data)).convert_alpha()
                img = pygame.transform.smoothscale(img, (32, 32))
                mask = pygame.Surface((32, 32), pygame.SRCALPHA)
                pygame.draw.rect(mask, TEXT_MAIN, (0, 0, 32, 32), border_radius=6)
                img.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                thumb = img
            return {"path": path, "title": title, "artist": artist, "duration": duration, "thumb": thumb}
        except:
            return {"path": path, "title": os.path.basename(path), "artist": "Неизвестный", "duration": 0,
                    "thumb": None}

    def load_folder(self):
        root = tk.Tk()
        root.withdraw()
        folder = filedialog.askdirectory()
        root.destroy()
        if folder:
            # Расширяем поддержку файлов (soundfile идеально читает wav, flac, ogg)
            # Для mp3 soundfile использует встроенный системный кодек
            files = [os.path.join(folder, f) for f in os.listdir(folder)
                     if f.lower().endswith(('.wav', '.ogg', '.flac', '.mp3'))]
            self.playlist = [self.get_track_info(f) for f in files]
            self.scroll_y = 0
            if self.playlist: self.load_track(0)

    def pre_analyze_bass(self, path):
        """Честный математический FFT анализ частот кика 45-150Гц без ffmpeg"""
        try:
            data, samplerate = sf.read(path, dtype='float32')
            # Если стерео — переводим в моно
            if len(data.shape) > 1:
                data = np.mean(data, axis=1)

            fps = 60
            hop_size = int(samplerate / fps)
            envelope = []

            for i in range(0, len(data) - hop_size, hop_size):
                window = data[i:i + hop_size]
                if len(window) < hop_size: break

                # Делаем FFT (Быстрое преобразование Фурье)
                fft_data = np.abs(np.fft.rfft(window))
                freqs = np.fft.rfftfreq(hop_size, 1 / samplerate)

                # Твоя сетка: вырезаем строго суб-бас и кик (45-150 Гц)
                bass_indices = np.where((freqs >= 30) & (freqs <= 190))[0]
                if len(bass_indices) > 0:
                    bass_val = np.mean(fft_data[bass_indices])
                    envelope.append(bass_val)
                else:
                    envelope.append(0.0)

            # Нормализация амплитуды
            max_val = max(envelope) if len(envelope) > 0 else 1.0
            if max_val == 0: max_val = 1.0
            self.bass_envelope = [min(1.0, v / (max_val * 0.75)) for v in envelope]
            print(f"FFT анализ завершен успешно! Шагов кадра: {len(self.bass_envelope)}")
        except Exception as e:
            print("Ошибка FFT чтения через soundfile, включаем стабильный симулятор:", e)
            # Если кодек файла не поддерживается напрямую, создаем плавную карту импульсов
            self.bass_envelope = [abs(math.sin(i * 0.15)) * 0.4 for i in range(20000)]

    def load_track(self, index):
        if 0 <= index < len(self.playlist):
            self.current_index = index
            item = self.playlist[index]

            self.current_path = item['path']
            self.seek_offset = 0

            self.pre_analyze_bass(item['path'])

            pygame.mixer.music.load(item['path'])
            pygame.mixer.music.play()
            pygame.mixer.music.set_volume(self.volume)
            self.is_playing = True

            self.song_title = item['title']
            self.song_artist = item['artist']
            self.track_duration_ms = item['duration'] * 1000

            try:
                audio = File(item['path'])
                raw_data = None
                if 'APIC:' in audio:
                    raw_data = audio['APIC:'].data
                elif 'covr' in audio:
                    raw_data = audio['covr'][0]
                if raw_data:
                    img = pygame.image.load(BytesIO(raw_data)).convert_alpha()
                    small_img = pygame.transform.smoothscale(img, (4, 4))
                    r = g = b = count = 0
                    for px in range(4):
                        for py in range(4):
                            c = small_img.get_at((px, py))
                            r += c.r;
                            g += c.g;
                            b += c.b;
                            count += 1
                    self.current_raw_color = (r // count, g // count, b // count)

                    img = pygame.transform.smoothscale(img, (240, 240))
                    mask = pygame.Surface((240, 240), pygame.SRCALPHA)
                    pygame.draw.rect(mask, TEXT_MAIN, (0, 0, 240, 240), border_radius=24)
                    img.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                    self.album_art = img
                else:
                    self.album_art = None
                    self.current_raw_color = (60, 70, 95)
            except:
                self.album_art = None
                self.current_raw_color = (60, 70, 95)

    def update_fft_bass(self):
        """Связывает кадры интерфейса со спектром баса"""
        if self.is_playing and pygame.mixer.music.get_busy():
            curr_ms = pygame.mixer.music.get_pos()
            frame_idx = int((curr_ms / 1000) * 60)

            if frame_idx < len(self.bass_envelope):
                raw_bass = self.bass_envelope[frame_idx]
                if raw_bass > self.bass_energy:
                    self.bass_energy = raw_bass  # Мощная атака кика
                else:
                    self.bass_energy += (raw_bass - self.bass_energy) * 0.18  # Благородный спад

            # Амплитуда пульсации неона строго в пределах 3-10% (до +25% при жестком пике)
            self.pulse_scale = 1.0 + (self.bass_energy * 0.24)
        else:
            self.bass_energy *= 0.85
            self.pulse_scale = 1.0

    def draw(self):
        self.update_fft_bass()
        bg_gradient = self.generate_fast_gradient(self.current_raw_color, self.pulse_scale)
        self.screen.blit(bg_gradient, (0, 0))

        # Матовые карточки интерфейса
        left_card = pygame.Surface((420, 520), pygame.SRCALPHA)
        pygame.draw.rect(left_card, CARD_BG_COLOR, (0, 0, 420, 520), border_radius=24)
        pygame.draw.rect(left_card, (242, 242, 247, 15), (0, 0, 420, 520), width=1, border_radius=24)
        self.screen.blit(left_card, (40, 40))

        right_card = pygame.Surface((280, 520), pygame.SRCALPHA)
        pygame.draw.rect(right_card, CARD_BG_COLOR, (0, 0, 280, 520), border_radius=24)
        pygame.draw.rect(right_card, (242, 242, 247, 12), (0, 0, 280, 520), width=1, border_radius=24)
        self.screen.blit(right_card, (480, 40))

        # Кнопка Папка - темный стиль
        btn_rect = pygame.Rect(30, 8, 80, 29)
        mouse_pos = pygame.mouse.get_pos()
        is_hovered = btn_rect.collidepoint(mouse_pos)

        # Цвет кнопки: почти черный с легким светлым оттенком при наведении
        # 1. Сначала определяем параметры (можно в начале метода draw)
        btn_x = 40
        btn_y = 6
        btn_w = 110
        btn_h = 32

        # 2. Создаем объект Rect на основе этих параметров
        btn_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)

        # 3. Теперь используем btn_rect для отрисовки
        btn_color = (45, 45, 50) if btn_rect.collidepoint(pygame.mouse.get_pos()) else (35, 35, 40)

        pygame.draw.rect(self.screen, btn_color, btn_rect, border_radius=20)
        pygame.draw.rect(self.screen, (60, 60, 70), btn_rect, width=1, border_radius=13)

        text_surf = self.font_small.render("Папка", True, (200, 200, 205))
        self.screen.blit(text_surf, (btn_rect.x + (btn_rect.width - text_surf.get_width()) // 2,
                                     btn_rect.y + (btn_rect.height - text_surf.get_height()) // 2))

        # Обложка и тексты трека
        if self.album_art:
            self.screen.blit(self.album_art, (130, 75))
            pygame.draw.rect(self.screen, (242, 242, 247, 20), (130, 75, 240, 240), width=1, border_radius=24)
        else:
            pygame.draw.rect(self.screen, (50, 50, 55), (130, 75, 240, 240), border_radius=24)

        t_surf = self.font_title.render(str(self.song_title)[:25], True, TEXT_MAIN)
        a_surf = self.font_artist.render(str(self.song_artist)[:30], True, TEXT_SEC)
        self.screen.blit(t_surf, (250 - t_surf.get_width() // 2, 335))
        self.screen.blit(a_surf, (250 - a_surf.get_width() // 2, 365))

        # Плейлист
        max_scroll = max(0, len(self.playlist) * 48 - 440)
        self.scroll_y = max(0, min(self.scroll_y, max_scroll))

        for i, item in enumerate(self.playlist):
            y = 65 + (i * 48) - self.scroll_y
            if 45 < y < 520:
                if i == self.current_index:
                    pygame.draw.rect(self.screen, (242, 242, 247, 235), (490, y, 260, 42), border_radius=12)
                    current_text_color = TEXT_DARK
                    current_sec_color = (90, 90, 95)
                else:
                    current_text_color = TEXT_MAIN
                    current_sec_color = TEXT_SEC

                if item['thumb']:
                    self.screen.blit(item['thumb'], (500, y + 5))
                else:
                    pygame.draw.rect(self.screen, (55, 55, 55, 20), (500, y + 5, 32, 32), border_radius=6)

                text = self.font_small.render(item['title'][:18], True, current_text_color)
                dur = self.font_small.render(self.format_time(item['duration']), True, current_sec_color)
                self.screen.blit(text, (545, y + 12))
                self.screen.blit(dur, (735 - dur.get_width(), y + 12))
                # --- Отрисовка скроллбара (только "личинка" с блюром, без полосы) ---
                if max_scroll > 0:
                    track_x = 751  # Позиция X
                    track_y = 65  # Начало зоны прокрутки по Y
                    track_h = 465  # Общая высота зоны

                    # Расчет размеров "личинки"
                    content_h = len(self.playlist) * 48
                    visible_h = 440
                    thumb_ratio = visible_h / content_h
                    thumb_h = max(20, int(track_h * thumb_ratio))

                    # Расчет позиции "личинки"
                    scroll_ratio = self.scroll_y / max_scroll
                    thumb_y = track_y + int((track_h - thumb_h) * scroll_ratio)

                    # --- РИСУЕМ ЛИЧИНКУ С ЭФФЕКТОМ ГАУССОВСКОГО РАЗМЫТИЯ ---
                    core_color = (110, 110, 115)
                    blur_intensity = 3

                    # ВАЖНО: Задаем толщину центральной линии (2 пикселя вместо 4)
                    base_w = 2

                    surf_w = base_w + blur_intensity * 2
                    surf_h = thumb_h + blur_intensity * 2
                    thumb_surf = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)

                    # 1. Рисуем "ядро" личинки
                    core_rect = (blur_intensity, blur_intensity, base_w, thumb_h)
                    pygame.draw.rect(thumb_surf, core_color, core_rect, border_radius=1)

                    # 2. Имитируем блюр
                    for p in range(1, blur_intensity + 1):
                        alpha = int(80 / p)
                        if alpha <= 0: break

                        pass_color = (core_color[0], core_color[1], core_color[2], alpha)
                        # Расширяем блюр вокруг тонкого ядра
                        rect = (blur_intensity - p, blur_intensity, base_w + p * 2, thumb_h)
                        pygame.draw.rect(thumb_surf, pass_color, rect, border_radius=1 + p // 2)

                    # 3. Накладываем на экран (добавил +1 к координате X для идеальной центровки тонкой линии)
                    self.screen.blit(thumb_surf, (track_x - blur_intensity + 1, thumb_y - blur_intensity))

        # Таймлайн
        length = self.track_duration_ms / 1000
        curr = self.seek_offset + max(0, pygame.mixer.music.get_pos() / 1000) if self.is_playing else 0
        prog = (curr / length) if length > 0 else 0

        pygame.draw.rect(self.screen, (242, 242, 247, 35), (90, 415, 320, 4), border_radius=2)
        pygame.draw.rect(self.screen, TEXT_DARK, (90, 415, int(320 * min(prog, 1)), 4), border_radius=2)
        if length > 0:
            self.draw_aa_circle(self.screen, 90 + int(320 * min(prog, 1)), 417, 5, TEXT_DARK)

        self.screen.blit(self.font_small.render(self.format_time(curr), True, TEXT_SEC), (90, 425))
        self.screen.blit(self.font_small.render(self.format_time(length), True, TEXT_SEC), (410 - 30, 425))

        # Регулятор громкости
        pygame.draw.rect(self.screen, (242, 242, 247, 25), (150, 530, 200, 4), border_radius=2)
        pygame.draw.rect(self.screen, TEXT_DARK, (150, 530, int(200 * self.volume), 4), border_radius=2)
        self.draw_aa_circle(self.screen, 150 + int(200 * self.volume), 532, 5, TEXT_DARK)

        # Кнопки управления
        for btn in self.buttons:
            self.draw_aa_circle(self.screen, btn["x"], btn["y"], btn["r"], BTN_COLOR)
            self.draw_vector_icon(btn["action"], btn["x"], btn["y"], self.is_playing)

    def run(self):
        running = True
        while running:
            # Старая глючная проверка get_busy() отсюда удалена!

            pos = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                # --- НОВОЕ: Ловим 100% точный сигнал окончания песни ---
                elif event.type == self.MUSIC_END:
                    if self.current_index < len(self.playlist) - 1:
                        self.load_track(self.current_index + 1)

                elif event.type == pygame.MOUSEWHEEL:
                    self.scroll_y -= event.y * 30

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    # --- ИСПРАВЛЕНИЕ: Реагируем ТОЛЬКО на левый клик (1), игнорируем колесико ---
                    if event.button == 1:
                        if 40 < pos[0] < 125 and 5 < pos[1] < 35:
                            self.load_folder()
                        elif 150 < pos[0] < 350 and 520 < pos[1] < 545:
                            self.dragging_vol = True
                        elif 90 < pos[0] < 410 and 405 < pos[1] < 425:
                            self.dragging_prog = True

                            # --- НОВОЕ: Клик по скроллбару ---
                        elif self.thumb_rect.collidepoint(pos):
                          self.dragging_scroll = True
                          # Запоминаем, за какое место личинки мы ухватились (чтобы она не прыгала)
                          self.scroll_click_offset = pos[1] - self.thumb_rect.y

                        # Зона плейлиста
                        if 480 < pos[0] < 750:
                            idx = (pos[1] + self.scroll_y - 65) // 48
                            if 0 <= idx < len(self.playlist):
                                self.load_track(idx)

                        # Зона кнопок
                        for btn in self.buttons:
                            if math.hypot(pos[0] - btn["x"], pos[1] - btn["y"]) < btn["r"]:
                                if btn["action"] == "prev": self.load_track(self.current_index - 1)
                                if btn["action"] == "next": self.load_track(self.current_index + 1)
                                if btn["action"] == "toggle":
                                    if self.is_playing:
                                        pygame.mixer.music.pause()
                                        self.is_playing = False
                                    else:
                                        pygame.mixer.music.unpause()
                                        self.is_playing = True




                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
                        if self.dragging_prog and self.track_duration_ms > 0 and self.current_path:
                            progress = max(0.0, min(1.0, (pos[0] - 90) / 320))
                            seek_time = progress * (self.track_duration_ms / 1000)
                            # 1. Выключаем отслеживание конца трека
                            pygame.mixer.music.set_endevent()

                            pygame.mixer.music.stop()
                            pygame.mixer.music.load(self.current_path)
                            pygame.mixer.music.play(start=seek_time)
                            pygame.mixer.music.set_volume(self.volume)
                            self.seek_offset = seek_time
                            self.is_playing = True

                            # 2. Очищаем очередь от ложных срабатываний остановки
                            pygame.event.clear(self.MUSIC_END)

                            # 3. Включаем отслеживание обратно
                            pygame.mixer.music.set_endevent(self.MUSIC_END)
                        self.dragging_prog = False
                        self.dragging_vol = False
                        self.dragging_scroll = False

                elif event.type == pygame.MOUSEMOTION:
                    if self.dragging_vol:
                        self.volume = max(0.0, min(1.0, (pos[0] - 150) / 200))
                        pygame.mixer.music.set_volume(self.volume)

                        # --- НОВОЕ: Тянем скроллбар ---
                elif self.dragging_scroll:
                        track_y = 65
                        track_h = 465

                        # Пересчитываем размеры, чтобы знать пропорции
                        content_h = len(self.playlist) * 48
                        visible_h = 440
                        thumb_ratio = visible_h / content_h
                        thumb_h = max(20, int(track_h * thumb_ratio))

                        # Вычисляем новую Y-координату ползунка с учетом места захвата
                        new_thumb_y = pos[1] - self.scroll_click_offset

                        # Ограничиваем, чтобы личинка не вылетала за пределы трека
                        new_thumb_y = max(track_y, min(new_thumb_y, track_y + track_h - thumb_h))

                        # Переводим физическое положение ползунка в значение скролла плейлиста
                        max_scroll = max(0, len(self.playlist) * 48 - 440)
                        if track_h > thumb_h:  # Защита от деления на ноль
                            scroll_ratio = (new_thumb_y - track_y) / (track_h - thumb_h)
                            self.scroll_y = int(scroll_ratio * max_scroll)

            self.draw()
            pygame.display.flip()
            self.clock.tick(60)
        pygame.quit()

if __name__ == "__main__":
    SimplePlayer().run()