# Real-time Collaboration Application

This project is a real-time collaboration application that allows multiple users to edit text documents simultaneously using WebSocket technology. It consists of a client-side React application and a server-side WebSocket server.

## Project Structure

```
realtime-collab-app
├── client
│   ├── src
│   │   ├── App.tsx                  # Main entry point for the client application
│   │   ├── components
│   │   │   └── CollaborativeEditor.tsx # Component for collaborative text editing
│   │   └── services
│   │       └── websocket.ts          # WebSocket connection management
│   ├── package.json                  # Client dependencies and scripts
│   └── tsconfig.json                 # TypeScript configuration for the client
├── server
│   ├── src
│   │   ├── index.ts                  # Entry point for the server application
│   │   ├── rooms
│   │   │   └── roomManager.ts        # Manages collaborative editing rooms
│   │   └── types
│   │       └── index.ts              # Type definitions for WebSocket messages
│   ├── package.json                  # Server dependencies and scripts
│   └── tsconfig.json                 # TypeScript configuration for the server
├── package.json                      # Overall project dependencies and scripts
└── README.md                         # Project documentation
```

## Getting Started

### Prerequisites

- Node.js (v14 or later)
- TypeScript (v4 or later)

### Installation

1. Clone the repository:

   ```
   git clone <repository-url>
   cd realtime-collab-app
   ```

2. Install dependencies for both client and server:

   ```
   cd client
   npm install
   cd ../server
   npm install
   ```

### Running the Application

1. Start the server:

   ```
   cd server
   npm start
   ```

2. Start the client:

   ```
   cd client
   npm start
   ```

3. Open your browser and navigate to `http://localhost:3000` to access the application.

### Usage

- Users can create or join collaborative editing rooms.
- Changes made by one user will be reflected in real-time for all users in the same room.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any enhancements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for details.