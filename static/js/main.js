const socket = io();

// --- 1. СОХРАНЕНИЕ НИКА НА ГЛАВНОЙ СТРАНИЦЕ ---
const usernameInput = document.getElementById('username-input');
if (usernameInput) {
    const savedName = localStorage.getItem('word_game_username');
    if (!usernameInput.value && savedName) {
        usernameInput.value = savedName;
    }
    usernameInput.addEventListener('input', () => {
        localStorage.setItem('word_game_username', usernameInput.value.trim());
    });
}

// --- 2. ЛОГИКА СТРАНИЦЫ ЛОББИ ---
const lobbyCard = document.getElementById('lobby-card');
if (lobbyCard) {
    const roomCode = lobbyCard.dataset.room;
    const username = lobbyCard.dataset.username;
    const isHost = lobbyCard.dataset.ishost === 'true';
    
    const hostNameEl = document.getElementById('host-name');
    const playersList = document.getElementById('players-list');
    const startGameBtn = document.getElementById('start-game-btn');

    socket.emit('join_lobby', { room_code: roomCode, username: username });

    socket.on('update_lobby', (data) => {
        hostNameEl.textContent = data.host;
        playersList.innerHTML = '';
        const guests = data.players.filter(name => name !== data.host);

        if (guests.length === 0) {
            const emptyLi = document.createElement('li');
            emptyLi.textContent = 'Ожидание друзей...';
            emptyLi.style.opacity = '0.6';
            playersList.appendChild(emptyLi);
        } else {
            guests.forEach(name => {
                const li = document.createElement('li');
                li.textContent = name;
                playersList.appendChild(li);
            });
        }
    });

    if (isHost && startGameBtn) {
        startGameBtn.addEventListener('click', () => {
            socket.emit('start_game', { room_code: roomCode });
        });
    }

    // Переход на страницу игры в ЭТОЙ ЖЕ вкладке
    socket.on('game_started', (data) => {
        window.location.href = `/game/${data.room_code}`;
    });
}

// --- 3. ЛОГИКА СТРАНИЦЫ ИГРЫ (game.html) ---
const gameCard = document.getElementById('game-card');
if (gameCard) {
    const roomCode = gameCard.dataset.room;
    // Берём имя из карточки (или из localStorage на случай двух вкладок)
    const myUsername = gameCard.dataset.username;

    const wordSubmitPhase = document.getElementById('word-submit-phase');
    const mainGamePhase = document.getElementById('main-game-phase');
    const gameOverPhase = document.getElementById('game-over-phase');

    const submitFormBox = document.getElementById('submit-form-box');
    const waitingOthersMsg = document.getElementById('waiting-others-msg');
    const readyCountEl = document.getElementById('ready-count');
    const secretWordInput = document.getElementById('secret-word-input');
    const submitWordBtn = document.getElementById('submit-word-btn');

    const gamePlayersList = document.getElementById('game-players-list');
    const answerBanner = document.getElementById('answer-banner');

    const btnYes = document.getElementById('btn-yes');
    const btnNo = document.getElementById('btn-no');
    const btnFinish = document.getElementById('btn-finish');

    socket.emit('join_game_room', { room_code: roomCode, username: myUsername });

    // Отправка загаданного слова
    submitWordBtn.addEventListener('click', () => {
        const word = secretWordInput.value.trim();
        if (!word) return alert('Введи слово!');
        
        socket.emit('submit_word', { room_code: roomCode, username: myUsername, word: word });
        submitFormBox.style.display = 'none';
        waitingOthersMsg.style.display = 'block';
    });

    socket.on('word_progress', (data) => {
        readyCountEl.textContent = `${data.ready}/${data.total}`;
    });

    // Отрисовка игрового поля, слов и блокировка кнопок по цветам
    socket.on('update_game_board', (data) => {
        wordSubmitPhase.style.display = 'none';
        mainGamePhase.style.display = 'block';

        if (data.last_answer) {
            answerBanner.textContent = data.last_answer;
        }

        // Определяем роль текущего игрока
        const isAnswerer = (myUsername === data.answerer); // Жёлтый
        const isGuesser = (myUsername === data.guesser);   // Зелёный

        // Кнопки ДА и НЕТ активны ТОЛЬКО у жёлтого игрока
        btnYes.disabled = !isAnswerer;
        btnNo.disabled = !isAnswerer;
        btnYes.style.opacity = isAnswerer ? '1' : '0.35';
        btnNo.style.opacity = isAnswerer ? '1' : '0.35';
        btnYes.style.cursor = isAnswerer ? 'pointer' : 'not-allowed';
        btnNo.style.cursor = isAnswerer ? 'pointer' : 'not-allowed';

        // Кнопка ЗАКОНЧИТЬ активна у зелёного и жёлтого
        const canFinish = (isGuesser || isAnswerer);
        btnFinish.disabled = !canFinish;
        btnFinish.style.opacity = canFinish ? '1' : '0.35';
        btnFinish.style.cursor = canFinish ? 'pointer' : 'not-allowed';

        gamePlayersList.innerHTML = '';
        data.players.forEach(p => {
            const li = document.createElement('li');
            li.className = 'player-word-item';

            const displayedWord = (p.name === myUsername) ? '??? (Угадай!)' : p.word;

            li.innerHTML = `
                <div class="pw-text">
                    <span class="pw-name">${p.name}</span> : <span class="pw-word">${displayedWord}</span>
                </div>
                <span class="status-dot dot-${p.status}" title="${p.status}"></span>
            `;
            gamePlayersList.appendChild(li);
        });
    });

    // Кнопки справа: только ДА, НЕТ и Закончить (без btn-next-turn!)
    btnYes.addEventListener('click', () => {
        socket.emit('send_answer', { room_code: roomCode, username: myUsername, answer: 'ДА' });
    });

    btnNo.addEventListener('click', () => {
        socket.emit('send_answer', { room_code: roomCode, username: myUsername, answer: 'НЕТ' });
    });

    btnFinish.addEventListener('click', () => {
        socket.emit('finish_game', { room_code: roomCode, username: myUsername });
    });

    // Финал игры
    socket.on('game_finished', (data) => {
        mainGamePhase.style.display = 'none';
        gameOverPhase.style.display = 'block';
        document.getElementById('winner-text').textContent = `Игру завершил: ${data.finished_by}`;

        const finalList = document.getElementById('final-words-list');
        finalList.innerHTML = '';
        for (const [player, word] of Object.entries(data.assigned_words)) {
            const li = document.createElement('li');
            li.className = 'player-word-item';
            li.innerHTML = `<div class="pw-text"><b>${player}</b> : <span class="pw-word">${word}</span></div>`;
            finalList.appendChild(li);
        }
    });
}