from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uuid
import asyncio
from typing import Dict, List, Optional, Set, Tuple

# Models
class Player:
    def __init__(self, name: str):
        self.id = str(uuid.uuid4())
        self.name = name
        self.websocket: Optional[WebSocket] = None
        self.game_id: Optional[str] = None

class Game:
    def __init__(self, player1_id: str, player2_id: str):
        self.id = str(uuid.uuid4())
        self.board = [[None for _ in range(3)] for _ in range(3)]
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.current_player_id = player1_id  # Player 1 starts
        self.winner = None
        self.is_draw = False
        self.marks = {player1_id: "X", player2_id: "O"}
    
    def make_move(self, player_id: str, row: int, col: int) -> bool:
        # Check if it's the player's turn
        if player_id != self.current_player_id:
            return False
        
        # Check if the cell is empty
        if self.board[row][col] is not None:
            return False
        
        # Make the move
        self.board[row][col] = self.marks[player_id]
        
        # Check for win or draw
        self.check_game_state()
        
        # Switch player
        if not self.winner and not self.is_draw:
            self.current_player_id = self.player2_id if self.current_player_id == self.player1_id else self.player1_id
        
        return True
    
    def check_game_state(self):
        # Check rows
        for row in self.board:
            if row[0] is not None and row[0] == row[1] == row[2]:
                self.winner = self.player1_id if row[0] == "X" else self.player2_id
                return
        
        # Check columns
        for col in range(3):
            if (self.board[0][col] is not None and 
                self.board[0][col] == self.board[1][col] == self.board[2][col]):
                self.winner = self.player1_id if self.board[0][col] == "X" else self.player2_id
                return
        
        # Check diagonals
        if (self.board[0][0] is not None and 
            self.board[0][0] == self.board[1][1] == self.board[2][2]):
            self.winner = self.player1_id if self.board[0][0] == "X" else self.player2_id
            return
        
        if (self.board[0][2] is not None and 
            self.board[0][2] == self.board[1][1] == self.board[2][0]):
            self.winner = self.player1_id if self.board[0][2] == "X" else self.player2_id
            return
        
        # Check for draw
        is_full = all(cell is not None for row in self.board for cell in row)
        if is_full:
            self.is_draw = True
    
    def get_state(self):
        return {
            "id": self.id,
            "board": self.board,
            "currentPlayer": self.current_player_id,
            "winner": self.winner,
            "isDraw": self.is_draw,
            "player1": self.player1_id,
            "player2": self.player2_id,
            "marks": self.marks
        }

# Game Manager
class GameManager:
    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.games: Dict[str, Game] = {}
        self.waiting_players: Set[str] = set()
    
    def add_player(self, name: str) -> Player:
        player = Player(name)
        self.players[player.id] = player
        return player
    
    def remove_player(self, player_id: str):
        if player_id in self.waiting_players:
            self.waiting_players.remove(player_id)
        
        if player_id in self.players:
            player = self.players[player_id]
            if player.game_id and player.game_id in self.games:
                # End the game if a player disconnects
                game = self.games[player.game_id]
                other_player_id = game.player1_id if player_id == game.player2_id else game.player2_id
                if other_player_id in self.players:
                    other_player = self.players[other_player_id]
                    asyncio.create_task(self.send_game_ended(other_player, "Opponent disconnected"))
                
                del self.games[player.game_id]
            
            del self.players[player_id]
    
    def add_to_waiting(self, player_id: str):
        self.waiting_players.add(player_id)
        self.try_matchmaking()
    
    def try_matchmaking(self) -> Optional[Game]:
        if len(self.waiting_players) >= 2:
            player1_id = next(iter(self.waiting_players))
            self.waiting_players.remove(player1_id)
            
            player2_id = next(iter(self.waiting_players))
            self.waiting_players.remove(player2_id)
            
            game = Game(player1_id, player2_id)
            self.games[game.id] = game
            
            # Update players with game ID
            self.players[player1_id].game_id = game.id
            self.players[player2_id].game_id = game.id
            
            return game
        return None
    
    def make_move(self, player_id: str, game_id: str, row: int, col: int) -> bool:
        if game_id not in self.games:
            return False
        
        game = self.games[game_id]
        return game.make_move(player_id, row, col)
    
    async def send_game_state(self, game_id: str):
        if game_id not in self.games:
            return
        
        game = self.games[game_id]
        state = game.get_state()
        
        player1 = self.players.get(game.player1_id)
        player2 = self.players.get(game.player2_id)
        
        if player1 and player1.websocket:
            await player1.websocket.send_json({
                "type": "game_state",
                "data": state,
                "yourTurn": game.current_player_id == game.player1_id
            })
        
        if player2 and player2.websocket:
            await player2.websocket.send_json({
                "type": "game_state",
                "data": state,
                "yourTurn": game.current_player_id == game.player2_id
            })
        
        # If game is over, clean up
        if game.winner or game.is_draw:
            # Wait a bit before removing the game to allow clients to see the final state
            await asyncio.sleep(5)
            if game_id in self.games:
                del self.games[game_id]
    
    async def send_game_ended(self, player: Player, reason: str):
        if player.websocket:
            await player.websocket.send_json({
                "type": "game_ended",
                "reason": reason
            })

# FastAPI app
app = FastAPI()
game_manager = GameManager()

# Request models
class PlayerRegistration(BaseModel):
    name: str

class MoveRequest(BaseModel):
    game_id: str
    row: int
    col: int

# Routes
@app.post("/register")
async def register_player(player_data: PlayerRegistration):
    player = game_manager.add_player(player_data.name)
    return {"player_id": player.id, "name": player.name}

@app.post("/join-queue")
async def join_queue(player_id: str):
    if player_id not in game_manager.players:
        raise HTTPException(status_code=404, detail="Player not found")
    
    game_manager.add_to_waiting(player_id)
    return {"status": "waiting", "message": "Added to matchmaking queue"}

@app.websocket("/ws/{player_id}")
async def websocket_endpoint(websocket: WebSocket, player_id: str):
    await websocket.accept()
    
    if player_id not in game_manager.players:
        await websocket.close(code=1000, reason="Player not found")
        return
    
    player = game_manager.players[player_id]
    player.websocket = websocket
    
    try:
        # Send initial connection confirmation
        await websocket.send_json({"type": "connected", "player_id": player_id})
        
        # If player is already in a game, send the game state
        if player.game_id and player.game_id in game_manager.games:
            await game_manager.send_game_state(player.game_id)
        
        # Listen for messages
        while True:
            data = await websocket.receive_json()
            
            if data["type"] == "move":
                game_id = data["game_id"]
                row = data["row"]
                col = data["col"]
                
                if game_manager.make_move(player_id, game_id, row, col):
                    await game_manager.send_game_state(game_id)
    
    except WebSocketDisconnect:
        game_manager.remove_player(player_id)



# Mount static files (CSS and JS)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# HTML for the frontend
@app.get("/", response_class=HTMLResponse)
async def get_html():
    with open("app/templates/index.html", "r") as file:
        return file.read()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


print("Server would start on http://127.0.0.1:8000")