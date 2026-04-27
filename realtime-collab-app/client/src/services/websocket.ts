import { useEffect, useRef } from 'react';

const WEBSOCKET_URL = 'ws://localhost:4000'; // Update with your server URL

let socket: WebSocket | null = null;

export const connectWebSocket = (onMessage: (message: string) => void) => {
    socket = new WebSocket(WEBSOCKET_URL);

    socket.onopen = () => {
        console.log('WebSocket connection established');
    };

    socket.onmessage = (event) => {
        onMessage(event.data);
    };

    socket.onclose = () => {
        console.log('WebSocket connection closed');
    };

    socket.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
};

export const sendMessage = (message: string) => {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(message);
    } else {
        console.error('WebSocket is not open. Unable to send message:', message);
    }
};

export const disconnectWebSocket = () => {
    if (socket) {
        socket.close();
        socket = null;
    }
};