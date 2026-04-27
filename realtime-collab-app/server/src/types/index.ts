export interface Message {
    type: string;
    content: string;
    userId: string;
    timestamp: number;
}

export interface User {
    id: string;
    name: string;
}