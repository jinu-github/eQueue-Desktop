from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from db.database import Base, engine, SessionLocal
from db import models
from websocket_manager import manager
from routers import patients, queue, users, departments
from routers.users import hash_password

app = FastAPI(title="eQueue Desktop Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(patients.router)
app.include_router(queue.router)
app.include_router(users.router)
app.include_router(departments.router)


@app.on_event("startup")
def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Seed default departments (mirrors the original system)
        if db.query(models.Department).count() == 0:
            db.add_all([
                models.Department(name="Laboratory", avg_consultation_minutes=20),
                models.Department(name="Radiology", avg_consultation_minutes=25),
                models.Department(name="TB DOTS Unit", avg_consultation_minutes=10),
                models.Department(name="Outpatient Department (OPD)", avg_consultation_minutes=15),
            ])
            db.commit()

        # Seed default admin account
        if db.query(models.User).filter(models.User.username == "admin").count() == 0:
            db.add(models.User(
                username="admin",
                password_hash=hash_password("admin123"),
                full_name="System Administrator",
                role="admin",
            ))
            db.commit()
    finally:
        db.close()


@app.get("/")
def health_check():
    return {"status": "ok", "service": "eQueue Desktop Server"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # clients don't need to send anything
    except WebSocketDisconnect:
        manager.disconnect(websocket)
