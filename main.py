from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, Float, DateTime, LargeBinary, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from typing import List, Dict
from collections import deque
import statistics

app = FastAPI(title="Heartbeat Monitor API - Session Based")

# CORS untuk Android
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= DATABASE SETUP =================
DATABASE_URL = "postgresql://postgres:marcellganteng@localhost:5432/heartbeat_db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ================= NEW SESSION-BASED MODEL =================
class HeartbeatSession(Base):
    __tablename__ = "heartbeat_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, default="ESP32_001", index=True)
    
    # Timestamps
    session_start = Column(DateTime, default=datetime.utcnow)
    session_end = Column(DateTime, nullable=True)
    
    # BPM Statistics
    avg_bpm = Column(Float)
    min_bpm = Column(Float)
    max_bpm = Column(Float)
    
    # Beat Count
    total_beats = Column(Integer, default=0)
    
    # Duration
    duration_seconds = Column(Integer)
    
    # Waveform Samples (JSON string - sample setiap 10 beat)
    waveform_sample = Column(Text, nullable=True)
    
    # Audio Recording
    audio_data = Column(LargeBinary, nullable=True)
    
    # Quality Metrics
    avg_ir_value = Column(Float, nullable=True)
    signal_quality = Column(Float, nullable=True)  # 0-100%

# Create tables
Base.metadata.create_all(bind=engine)

# ================= SESSION MANAGER =================
class SessionManager:
    def __init__(self):
        self.active_sessions: Dict[str, dict] = {}
    
    def start_session(self, device_id: str):
        """Start new monitoring session"""
        print(f"🟢 Starting session for {device_id}")
        self.active_sessions[device_id] = {
            "start_time": datetime.utcnow(),
            "bpm_values": deque(maxlen=1000),  # Keep last 1000 BPM values
            "ir_values": deque(maxlen=1000),
            "beat_count": 0,
            "waveform_samples": []  # Sample setiap 10 beat
        }
        return self.active_sessions[device_id]
    
    def add_beat(self, device_id: str, bpm: float, ir: int, ac: int):
        """Add beat data to session"""
        if device_id not in self.active_sessions:
            self.start_session(device_id)
        
        session = self.active_sessions[device_id]
        
        # Only store valid BPM values
        if bpm > 0:
            session["bpm_values"].append(bpm)
        
        session["ir_values"].append(ir)
        session["beat_count"] += 1
        
        # Sample waveform every 10 beats
        if session["beat_count"] % 10 == 0:
            session["waveform_samples"].append({
                "beat_number": session["beat_count"],
                "bpm": round(bpm, 2),
                "ir": ir,
                "ac": ac,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Limit waveform samples to 500 (max ~5000 beats)
            if len(session["waveform_samples"]) > 500:
                session["waveform_samples"].pop(0)
    
    def get_session_info(self, device_id: str) -> dict:
        """Get current session info (untuk monitoring)"""
        if device_id not in self.active_sessions:
            return None
        
        session = self.active_sessions[device_id]
        bpm_list = list(session["bpm_values"])
        
        if not bpm_list:
            return {
                "active": True,
                "duration": (datetime.utcnow() - session["start_time"]).seconds,
                "beats": session["beat_count"],
                "avg_bpm": 0
            }
        
        return {
            "active": True,
            "duration": (datetime.utcnow() - session["start_time"]).seconds,
            "beats": session["beat_count"],
            "avg_bpm": round(statistics.mean(bpm_list), 1),
            "min_bpm": round(min(bpm_list), 1),
            "max_bpm": round(max(bpm_list), 1)
        }
    
    def end_session(self, device_id: str) -> dict:
        """End session and return summary"""
        if device_id not in self.active_sessions:
            print(f"⚠️ No active session for {device_id}")
            return None
        
        session = self.active_sessions[device_id]
        bpm_list = list(session["bpm_values"])
        ir_list = list(session["ir_values"])
        
        if not bpm_list or session["beat_count"] == 0:
            print(f"⚠️ Session has no valid data")
            del self.active_sessions[device_id]
            return None
        
        # Calculate signal quality (berapa % IR value > 50000)
        good_signal_count = sum(1 for ir in ir_list if ir > 50000)
        signal_quality = (good_signal_count / len(ir_list) * 100) if ir_list else 0
        
        duration = (datetime.utcnow() - session["start_time"]).seconds
        
        summary = {
            "device_id": device_id,
            "session_start": session["start_time"],
            "session_end": datetime.utcnow(),
            "duration_seconds": duration,
            "total_beats": session["beat_count"],
            "avg_bpm": round(statistics.mean(bpm_list), 2),
            "min_bpm": round(min(bpm_list), 2),
            "max_bpm": round(max(bpm_list), 2),
            "avg_ir_value": round(statistics.mean(ir_list), 2) if ir_list else 0,
            "signal_quality": round(signal_quality, 2),
            "waveform_sample": json.dumps(session["waveform_samples"])
        }
        
        print(f"🔴 Ending session for {device_id}: {session['beat_count']} beats, {duration}s, Avg BPM: {summary['avg_bpm']}")
        
        # Clear session
        del self.active_sessions[device_id]
        
        return summary

session_manager = SessionManager()

# ================= WEBSOCKET CONNECTION MANAGER =================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"📱 Client connected. Total: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"📱 Client disconnected. Total: {len(self.active_connections)}")
    
    async def broadcast(self, message: str):
        """Broadcast to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                disconnected.append(connection)
        
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

# ================= WEBSOCKET ENDPOINT =================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    device_id = None
    
    try:
        while True:
            data = await websocket.receive_text()
            
            try:
                json_data = json.loads(data)
                msg_type = json_data.get("type")
                
                # Session Start
                if msg_type == "session_start":
                    device_id = json_data.get("device_id", "ESP32_001")
                    session_manager.start_session(device_id)
                    print(f"🟢 Session started: {device_id}")
                    
                    # Send confirmation
                    await websocket.send_text(json.dumps({
                        "type": "session_started",
                        "device_id": device_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }))
                
                # Heartbeat Data (real-time)
                elif msg_type == "heartbeat":
                    device_id = json_data.get("device_id", "ESP32_001")
                    
                    # Add to session (NO DATABASE SAVE YET!)
                    session_manager.add_beat(
                        device_id,
                        json_data.get("bpm", 0),
                        json_data.get("ir", 0),
                        json_data.get("ac", 0)
                    )
                    
                    # Broadcast to all clients for real-time display
                    await manager.broadcast(json.dumps(json_data))
                
                # Session End (SAVE TO DATABASE HERE!)
                elif msg_type == "session_end":
                    device_id = json_data.get("device_id", "ESP32_001")
                    
                    # Get session summary
                    summary = session_manager.end_session(device_id)
                    
                    if summary:
                        # Save to database
                        db = SessionLocal()
                        try:
                            session_record = HeartbeatSession(**summary)
                            db.add(session_record)
                            db.commit()
                            db.refresh(session_record)
                            
                            print(f"✅ Session saved to DB: ID {session_record.id}")
                            
                            # Send confirmation with session ID
                            await websocket.send_text(json.dumps({
                                "type": "session_saved",
                                "session_id": session_record.id,
                                "summary": {
                                    "total_beats": summary["total_beats"],
                                    "avg_bpm": summary["avg_bpm"],
                                    "duration": summary["duration_seconds"]
                                }
                            }))
                            
                        except Exception as e:
                            print(f"❌ Database error: {e}")
                            db.rollback()
                        finally:
                            db.close()
                    else:
                        print(f"⚠️ No session data to save")
                
                # Get Session Info (untuk monitoring)
                elif msg_type == "get_session_info":
                    device_id = json_data.get("device_id", "ESP32_001")
                    info = session_manager.get_session_info(device_id)
                    
                    if info:
                        await websocket.send_text(json.dumps({
                            "type": "session_info",
                            "data": info
                        }))
                
            except json.JSONDecodeError:
                print("❌ Invalid JSON received")
            except Exception as e:
                print(f"❌ Error processing message: {e}")
    
    except WebSocketDisconnect:
        print(f"📱 Client disconnected")
        
        # Auto-save session if still active
        if device_id and device_id in session_manager.active_sessions:
            print(f"💾 Auto-saving session for {device_id}")
            summary = session_manager.end_session(device_id)
            
            if summary:
                db = SessionLocal()
                try:
                    session_record = HeartbeatSession(**summary)
                    db.add(session_record)
                    db.commit()
                    print(f"✅ Auto-saved session ID {session_record.id}")
                except Exception as e:
                    print(f"❌ Auto-save failed: {e}")
                    db.rollback()
                finally:
                    db.close()
        
        manager.disconnect(websocket)

# ================= HTTP ENDPOINTS =================
@app.get("/")
async def root():
    return {
        "message": "Heartbeat Monitor API - Session Based",
        "version": "2.0",
        "endpoints": {
            "websocket": "/ws",
            "sessions": "/sessions",
            "session_detail": "/sessions/{session_id}",
            "upload_audio": "/sessions/{session_id}/audio",
            "health": "/health",
            "stats": "/stats"
        }
    }

@app.get("/health")
async def health():
    db = SessionLocal()
    try:
        result = db.execute("SELECT 1").fetchone()
        db_status = "OK" if result else "Error"
    except Exception as e:
        db_status = f"Error: {str(e)}"
    finally:
        db.close()
    
    return {
        "status": "OK",
        "database": db_status,
        "active_connections": len(manager.active_connections),
        "active_sessions": len(session_manager.active_sessions)
    }

@app.get("/sessions")
async def get_sessions(limit: int = 50, device_id: str = None):
    """Get recent sessions"""
    db = SessionLocal()
    try:
        query = db.query(HeartbeatSession)
        
        if device_id:
            query = query.filter(HeartbeatSession.device_id == device_id)
        
        sessions = query.order_by(HeartbeatSession.session_start.desc()).limit(limit).all()
        
        return {
            "total": len(sessions),
            "sessions": [
                {
                    "id": s.id,
                    "device_id": s.device_id,
                    "start": s.session_start.isoformat(),
                    "end": s.session_end.isoformat() if s.session_end else None,
                    "duration": s.duration_seconds,
                    "total_beats": s.total_beats,
                    "avg_bpm": s.avg_bpm,
                    "min_bpm": s.min_bpm,
                    "max_bpm": s.max_bpm,
                    "signal_quality": s.signal_quality,
                    "has_audio": s.audio_data is not None
                }
                for s in sessions
            ]
        }
    finally:
        db.close()

@app.get("/sessions/{session_id}")
async def get_session_detail(session_id: int):
    """Get detailed session info including waveform"""
    db = SessionLocal()
    try:
        session = db.query(HeartbeatSession).filter(HeartbeatSession.id == session_id).first()
        
        if not session:
            return {"error": "Session not found"}
        
        waveform = json.loads(session.waveform_sample) if session.waveform_sample else []
        
        return {
            "id": session.id,
            "device_id": session.device_id,
            "start": session.session_start.isoformat(),
            "end": session.session_end.isoformat() if session.session_end else None,
            "duration": session.duration_seconds,
            "total_beats": session.total_beats,
            "avg_bpm": session.avg_bpm,
            "min_bpm": session.min_bpm,
            "max_bpm": session.max_bpm,
            "avg_ir_value": session.avg_ir_value,
            "signal_quality": session.signal_quality,
            "waveform_samples": waveform,
            "has_audio": session.audio_data is not None
        }
    finally:
        db.close()

@app.post("/sessions/{session_id}/audio")
async def upload_audio(session_id: int, audio_file: UploadFile = File(...)):
    """Upload audio for a session"""
    db = SessionLocal()
    try:
        session = db.query(HeartbeatSession).filter(HeartbeatSession.id == session_id).first()
        
        if not session:
            return {"status": "error", "message": "Session not found"}
        
        audio_bytes = await audio_file.read()
        session.audio_data = audio_bytes
        db.commit()
        
        return {
            "status": "success",
            "session_id": session_id,
            "audio_size": len(audio_bytes),
            "filename": audio_file.filename
        }
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

@app.get("/stats")
async def get_stats():
    """Get overall statistics"""
    db = SessionLocal()
    try:
        total_sessions = db.query(HeartbeatSession).count()
        total_beats = db.query(HeartbeatSession.total_beats).all()
        total_beats_sum = sum([b[0] for b in total_beats if b[0]])
        
        avg_bpm_all = db.query(HeartbeatSession.avg_bpm).all()
        avg_bpm_overall = statistics.mean([b[0] for b in avg_bpm_all if b[0]]) if avg_bpm_all else 0
        
        return {
            "total_sessions": total_sessions,
            "total_beats_recorded": total_beats_sum,
            "average_bpm_overall": round(avg_bpm_overall, 2),
            "active_sessions": len(session_manager.active_sessions),
            "active_connections": len(manager.active_connections)
        }
    finally:
        db.close()

@app.delete("/sessions")
async def delete_all_sessions():
    """Delete all sessions (testing only)"""
    db = SessionLocal()
    try:
        count = db.query(HeartbeatSession).delete()
        db.commit()
        return {"status": "success", "deleted": count}
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Heartbeat Monitor Server (Session-Based)")
    print("📊 Database: Session-based storage")
    print("🔄 Real-time: WebSocket broadcast enabled")
    uvicorn.run(app, host="0.0.0.0", port=8001)