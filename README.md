# Heartbeat Monitor - Session Based

Real-time heart rate monitoring system using ESP32, MAX30102 sensor, FastAPI backend, and Android app.

## Features

- ✅ Real-time BPM monitoring
- ✅ Session-based data storage (efficient!)
- ✅ WebSocket communication
- ✅ PostgreSQL database
- ✅ Android app support
- ✅ Audio recording capability
- ✅ OLED display on ESP32

## Tech Stack

**Hardware:**

- ESP32
- MAX30102 (Heart Rate & SpO2 sensor)
- OLED SSD1306

**Backend:**

- Python 3.10+
- FastAPI
- PostgreSQL
- WebSocket

**Frontend:**

- Android (Kotlin + Jetpack Compose)

## Installation

### 1. Backend Setup

```bash
# Clone repository
git clone https://github.com/marsel23xxx/api-heartbeat.git
cd api-heartbeat

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Setup PostgreSQL database
createdb heartbeat_db

# Run server
python main.py
```

Server will run at: http://localhost:8000

### 2. ESP32 Setup

1. Install Arduino IDE or PlatformIO
2. Install libraries:
   - DFRobot_MAX30102
   - Adafruit_GFX
   - Adafruit_SSD1306
   - ArduinoJson
   - WebSocketsClient
3. Update WiFi credentials in code
4. Update server IP address
5. Upload to ESP32

### 3. Android App

1. Open project in Android Studio
2. Update server URL in MainActivity.kt
3. Build & Run

## API Endpoints

```
GET  /                    - API info
GET  /health              - Health check
GET  /sessions            - Get all sessions
GET  /sessions/{id}       - Get session detail
POST /sessions/{id}/audio - Upload audio
GET  /stats               - Get statistics
```

## WebSocket Messages

**From ESP32:**

```json
{"type": "session_start", "device_id": "ESP32_001"}
{"type": "heartbeat", "bpm": 75, "ir": 105000, "ac": 120}
{"type": "session_end", "device_id": "ESP32_001"}
```

## Configuration

Edit `main.py`:

```python
DATABASE_URL = "postgresql://user:passwordkamu@localhost:5432/heartbeat_db"
```

Edit ESP32 code:

```cpp
const char* ssid = "YOUR_WIFI";
const char* password = "YOUR_PASSWORD";
const char* ws_host = "SERVER_IP";
```

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for VPS deployment instructions.

## License

MIT

## Author

Your Name - 2026
