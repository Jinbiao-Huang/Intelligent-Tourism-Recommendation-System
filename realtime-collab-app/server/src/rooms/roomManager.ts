class RoomManager {
    private rooms: Map<string, { users: Set<string>; messages: any[] }>;

    constructor() {
        this.rooms = new Map();
    }

    createRoom(roomId: string) {
        if (!this.rooms.has(roomId)) {
            this.rooms.set(roomId, { users: new Set(), messages: [] });
        }
    }

    addUserToRoom(roomId: string, userId: string) {
        const room = this.rooms.get(roomId);
        if (room) {
            room.users.add(userId);
        }
    }

    removeUserFromRoom(roomId: string, userId: string) {
        const room = this.rooms.get(roomId);
        if (room) {
            room.users.delete(userId);
        }
    }

    broadcastMessage(roomId: string, message: any) {
        const room = this.rooms.get(roomId);
        if (room) {
            room.messages.push(message);
            room.users.forEach(user => {
                // Logic to send message to each user
                // This could be a WebSocket send function
            });
        }
    }

    getMessages(roomId: string) {
        const room = this.rooms.get(roomId);
        return room ? room.messages : [];
    }
}

export default RoomManager;