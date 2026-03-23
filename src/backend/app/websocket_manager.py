import json
import logging
from typing import Dict, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Store active websocket connections
        # Optional: We could store them by subscription (e.g. which symbols they care about)
        # But for now a simple broadcast to all connected clients is fine for the MVP.
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info("websocket_client_connected total_clients=%s", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("websocket_client_disconnected total_clients=%s", len(self.active_connections))

    async def broadcast_json(self, data: dict):
        """Send a JSON message to all connected clients."""
        if not self.active_connections:
            return
            
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                logger.exception("websocket_broadcast_failed")
                disconnected.add(connection)
                
        # Clean up any connections that threw errors (e.g., client closed ungracefully)
        for conn in disconnected:
            self.disconnect(conn)

# Singleton instance to be used across the app
manager = ConnectionManager()
