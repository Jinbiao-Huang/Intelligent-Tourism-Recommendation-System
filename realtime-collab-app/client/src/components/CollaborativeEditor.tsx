import React, { useEffect, useRef, useState } from 'react';
import { connectWebSocket, sendMessage, onMessageReceived } from '../services/websocket';

const CollaborativeEditor: React.FC = () => {
    const [content, setContent] = useState('');
    const [roomId, setRoomId] = useState<string | null>(null);
    const editorRef = useRef<HTMLTextAreaElement | null>(null);

    useEffect(() => {
        const ws = connectWebSocket();

        ws.onopen = () => {
            if (roomId) {
                ws.send(JSON.stringify({ type: 'JOIN_ROOM', roomId }));
            }
        };

        onMessageReceived((message: string) => {
            const data = JSON.parse(message);
            if (data.type === 'UPDATE_CONTENT') {
                setContent(data.content);
            }
        });

        return () => {
            ws.close();
        };
    }, [roomId]);

    const handleChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
        const newContent = event.target.value;
        setContent(newContent);
        sendMessage({ type: 'UPDATE_CONTENT', content: newContent, roomId });
    };

    return (
        <div>
            <textarea
                ref={editorRef}
                value={content}
                onChange={handleChange}
                rows={10}
                cols={50}
            />
        </div>
    );
};

export default CollaborativeEditor;