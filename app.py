import random
import string
from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'word-game-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

rooms = {}

def generate_room_code(length=5):
    characters = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choices(characters, k=length))
        if code not in rooms:
            return code

@app.route('/')
def home():
    saved_username = session.get('username', '')
    return render_template('home.html', saved_username=saved_username)

@app.route('/create', methods=['POST'])
def create():
    username = request.form.get('username', 'Хост').strip()
    session['username'] = username
    
    room_code = generate_room_code(5)
    rooms[room_code] = {
        'host': username,
        'players': {},          # {sid: username}
        'submitted_words': {},  # {username: "загаданное слово"}
        'assigned_words': {},   # {username: "слово, которое ему надо угадать"}
        'turn_order': [],       # список ников по порядку очереди
        'guesser_idx': 0,       # индекс Зелёного игрока (отгадывает)
        'answerer_idx': 1,      # индекс Жёлтого игрока (отвечает Да/Нет)
        'game_started': False
    }
    return redirect(url_for('lobby', room_code=room_code))

@app.route('/join', methods=['POST'])
def join():
    username = request.form.get('username', 'Игрок').strip()
    room_code = request.form.get('room_code', '').strip().upper()
    session['username'] = username

    if not room_code:
        return render_template('home.html', error='Введи 5-значный код комнаты!', saved_username=username)
    if room_code not in rooms:
        return render_template('home.html', error='Комната с таким кодом не найдена!', saved_username=username)

    return redirect(url_for('lobby', room_code=room_code))

@app.route('/room/<room_code>')
def lobby(room_code):
    room_code = room_code.upper()
    if room_code not in rooms:
        return redirect(url_for('home'))
    
    # Сбрасываем состояние для новой игры при возврате в лобби
    rooms[room_code]['game_started'] = False
    rooms[room_code]['submitted_words'] = {}
    rooms[room_code]['assigned_words'] = {}

    username = session.get('username', 'Игрок')
    host_name = rooms[room_code]['host']
    is_host = (username == host_name)
    return render_template('lobby.html', room_code=room_code, username=username, host_name=host_name, is_host=is_host)

# НОВЫЙ МАРШРУТ: Страница самой игры
@app.route('/game/<room_code>')
def game(room_code):
    room_code = room_code.upper()
    if room_code not in rooms:
        return redirect(url_for('home'))
    username = session.get('username', 'Игрок')
    return render_template('game.html', room_code=room_code, username=username)

# --- СОКЕТЫ ЛОББИ ---
@socketio.on('join_lobby')
def handle_join_lobby(data):
    room_code = data['room_code']
    username = data['username']
    sid = request.sid

    if room_code in rooms:
        rooms[room_code]['players'][sid] = username
        join_room(room_code)
        emit('update_lobby', {
            'host': rooms[room_code]['host'],
            'players': list(dict.fromkeys(rooms[room_code]['players'].values()))
        }, to=room_code)

@socketio.on('start_game')
def handle_start_game(data):
    room_code = data['room_code']
    if room_code in rooms:
        rooms[room_code]['game_started'] = True
        rooms[room_code]['submitted_words'] = {}
        emit('game_started', {'room_code': room_code}, to=room_code)

# --- СОКЕТЫ ИГРЫ ---
@socketio.on('join_game_room')
def handle_join_game_room(data):
    room_code = data['room_code']
    username = data['username']
    sid = request.sid
    if room_code in rooms:
        rooms[room_code]['players'][sid] = username
        join_room(room_code)

@socketio.on('submit_word')
def handle_submit_word(data):
    room_code = data['room_code']
    username = data['username']
    word = data['word'].strip()

    if room_code not in rooms or not word:
        return

    room = rooms[room_code]
    room['submitted_words'][username] = word

    # Получаем список уникальных игроков в комнате
    all_players = list(dict.fromkeys(room['players'].values()))
    ready_count = len(room['submitted_words'])
    total_count = len(all_players)

    emit('word_progress', {'ready': ready_count, 'total': total_count}, to=room_code)

    # Когда ВСЕ игроки ввели свои слова — перемешиваем и начинаем!
    if ready_count >= total_count and total_count > 0:
        authors = list(room['submitted_words'].keys())
        random.shuffle(authors)

        # Сдвигаем слова по кругу на 1 человека, чтобы никому не попалось его собственное слово!
        assigned = {}
        for i in range(len(authors)):
            receiver = authors[i]
            word_owner = authors[(i + 1) % len(authors)]
            assigned[receiver] = room['submitted_words'][word_owner]

        room['assigned_words'] = assigned
        room['turn_order'] = authors
        room['guesser_idx'] = 0
        room['answerer_idx'] = 1 if len(authors) > 1 else 0

        send_board_state(room_code)

def send_board_state(room_code, last_answer=None):
    room = rooms[room_code]
    order = room['turn_order']
    n = len(order)
    
    guesser = order[room['guesser_idx'] % n]
    answerer = order[room['answerer_idx'] % n]

    players_info = []
    for p_name in order:
        # Определяем цвет кругляшка: green (отгадывает), yellow (отвечает), red (ждёт)
        if p_name == guesser:
            status = 'green'
        elif p_name == answerer:
            status = 'yellow'
        else:
            status = 'red'

        players_info.append({
            'name': p_name,
            'word': room['assigned_words'][p_name],
            'status': status
        })

    emit('update_game_board', {
        'players': players_info,
        'guesser': guesser,
        'answerer': answerer,
        'last_answer': last_answer
    }, to=room_code)

# Нажатие кнопок ДА или НЕТ (разрешено ТОЛЬКО жёлтому/оранжевому игроку)
@socketio.on('send_answer')
def handle_send_answer(data):
    room_code = data['room_code']
    answer = data['answer']  # "ДА" или "НЕТ"
    username = data['username']

    if room_code in rooms:
        room = rooms[room_code]
        n = len(room['turn_order'])
        if n == 0:
            return

        current_guesser = room['turn_order'][room['guesser_idx'] % n]
        current_answerer = room['turn_order'][room['answerer_idx'] % n]

        # ПРОВЕРКА: Нажимать ДА и НЕТ может ТОЛЬКО жёлтый/оранжевый игрок!
        if username != current_answerer:
            return

        if answer == 'НЕТ':
            # Сразу передаём ход следующей паре игроков
            if n > 1:
                room['guesser_idx'] = (room['guesser_idx'] + 1) % n
                room['answerer_idx'] = (room['guesser_idx'] + 1) % n
            
            next_guesser = room['turn_order'][room['guesser_idx'] % n]
            msg = f"{username} ответил: НЕТ ❌ — Ход переходит к {next_guesser}!"
        else:
            # При ответе ДА ход остаётся у того же зелёного игрока
            msg = f"{username} ответил: ДА ✅ — {current_guesser} продолжает угадывать!"

        send_board_state(room_code, last_answer=msg)

# Нажатие кнопки ЗАКОНЧИТЬ (разрешено зелёному и жёлтому игрокам)
@socketio.on('finish_game')
def handle_finish_game(data):
    room_code = data['room_code']
    username = data['username']
    if room_code in rooms:
        room = rooms[room_code]
        n = len(room['turn_order'])
        if n == 0:
            return

        current_guesser = room['turn_order'][room['guesser_idx'] % n]
        current_answerer = room['turn_order'][room['answerer_idx'] % n]

        # Красный игрок не может завершить игру
        if username not in (current_guesser, current_answerer):
            return

        emit('game_finished', {
            'finished_by': username,
            'assigned_words': room['assigned_words']
        }, to=room_code)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    for code, room in list(rooms.items()):
        if sid in room['players']:
            del room['players'][sid]
            emit('update_lobby', {
                'host': room['host'],
                'players': list(dict.fromkeys(room['players'].values()))
            }, to=code)
            break

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)