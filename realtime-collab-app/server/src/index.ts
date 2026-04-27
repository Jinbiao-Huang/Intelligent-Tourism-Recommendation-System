import express from 'express';
import http from 'http';
import { Server } from 'socket.io';
import { RoomManager } from './rooms/roomManager';

const app = express();
const server = http.createServer(app);
const io = new Server(server);
const roomManager = new RoomManager();

app.get('/', (req, res) => {
    res.send('WebSocket server is running');
});

io.on('connection', (socket) => {
    console.log('A user connected:', socket.id);

    socket.on('joinRoom', (roomId) => {
        roomManager.addUserToRoom(socket.id, roomId);
        socket.join(roomId);
        console.log(`User ${socket.id} joined room ${roomId}`);
    });

    socket.on('sendMessage', (roomId, message) => {
        roomManager.broadcastMessage(roomId, message, socket.id);
    });

    socket.on('disconnect', () => {
        roomManager.removeUser(socket.id);
        console.log('User disconnected:', socket.id);
    });
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});