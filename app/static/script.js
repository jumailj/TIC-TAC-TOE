let playerId = null;
let gameId = null;
let socket = null;
let playerMark = null;

// Show the registration form initially
document.getElementById('registration').style.display = 'block';

// Register player
document.getElementById('registerBtn').addEventListener('click', async () => {
    const name = document.getElementById('playerName').value.trim();
    if (!name) {
        alert('Please enter your name');
        return;
    }
    
    try {
        const response = await fetch('/register', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name })
        });
        
        const data = await response.json();
        playerId = data.player_id;
        
        // Join the queue
        await fetch(`/join-queue?player_id=${playerId}`, { method: 'POST' });
        
        // Connect WebSocket
        connectWebSocket();
        
        // Show waiting screen
        document.getElementById('registration').style.display = 'none';
        document.getElementById('waiting').style.display = 'block';
    } catch (error) {
        console.error('Error:', error);
        alert('An error occurred. Please try again.');
    }
});

function connectWebSocket() {
    socket = new WebSocket(`ws://${window.location.host}/ws/${playerId}`);
    
    socket.onopen = () => {
        console.log('WebSocket connected');
    };
    
    socket.onmessage = (event) => {
        const message = JSON.parse(event.data);
        console.log('Message received:', message);
        
        if (message.type === 'game_state') {
            gameId = message.data.id;
            
            // Determine player's mark
            if (playerId === message.data.player1) {
                playerMark = 'X';
            } else {
                playerMark = 'O';
            }
            
            // Show game screen
            document.getElementById('waiting').style.display = 'none';
            document.getElementById('gameContainer').style.display = 'block';
            
            // Update status
            updateStatus(message);
            
            // Render board
            renderBoard(message.data.board);
        } else if (message.type === 'game_ended') {
            alert(`Game ended: ${message.reason}`);
            // Reload page to start over
            window.location.reload();
        }
    };
    
    socket.onclose = () => {
        console.log('WebSocket disconnected');
    };
    
    socket.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

function updateStatus(message) {
    const statusElement = document.getElementById('status');
    const gameInfoElement = document.getElementById('gameInfo');
    
    if (message.data.winner) {
        const winnerName = message.data.winner === playerId ? 'You' : 'Opponent';
        statusElement.textContent = `Game over: ${winnerName} won!`;
    } else if (message.data.isDraw) {
        statusElement.textContent = 'Game over: Draw!';
    } else {
        statusElement.textContent = message.yourTurn ? 'Your turn' : "Opponent's turn";
    }
    
    gameInfoElement.textContent = `You are playing as ${playerMark}`;
}

function renderBoard(board) {
    const boardElement = document.getElementById('board');
    boardElement.innerHTML = '';
    
    for (let row = 0; row < 3; row++) {
        for (let col = 0; col < 3; col++) {
            const cell = document.createElement('div');
            cell.className = 'cell';
            cell.dataset.row = row;
            cell.dataset.col = col;
            cell.textContent = board[row][col] || '';
            
            cell.addEventListener('click', () => makeMove(row, col));
            
            boardElement.appendChild(cell);
        }
    }
}

function makeMove(row, col) {
    if (!gameId || !socket) return;
    
    socket.send(JSON.stringify({
        type: 'move',
        game_id: gameId,
        row: row,
        col: col
    }));
}