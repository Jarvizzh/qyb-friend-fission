import os
import uuid
import pandas as pd
import multiprocessing
import asyncio
import requests
import datetime
from typing import Dict, List
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from . import models, schemas, database
from .core.qyb_client import login_qyb
from .core.fission_engine import run_fission_task

app = FastAPI(title="企微宝好友裂变平台")

# 跨域配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 自动创建数据库表
models.Base.metadata.create_all(bind=database.engine)

# 任务管理
class TaskManager:
    def __init__(self):
        self.active_tasks: Dict[str, Dict] = {} # task_id -> {process, stop_event, log_queue}

    def start_task(self, task_id: str, tasks_list: List[dict], session_id: str, uid: str):
        log_queue = multiprocessing.Queue()
        stop_event = multiprocessing.Event()
        
        process = multiprocessing.Process(
            target=run_fission_task,
            args=(task_id, tasks_list, session_id, uid, log_queue, stop_event)
        )
        process.start()
        
        self.active_tasks[task_id] = {
            "process": process,
            "stop_event": stop_event,
            "log_queue": log_queue,
            "logs": []
        }
        return process.pid

    def stop_task(self, task_id: str):
        if task_id in self.active_tasks:
            self.active_tasks[task_id]["stop_event"].set()
            # 给予一点缓冲时间让子进程自行停止，否则强制杀死
            process = self.active_tasks[task_id]["process"]
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
            return True
        return False

task_manager = TaskManager()

# --- API 路由 ---

@app.get("/api/auth/check-status")
async def check_auth_status(db: Session = Depends(database.get_db)):
    config = db.query(models.SystemConfig).filter(models.SystemConfig.key == "secret_key").first()
    if not config:
        return {"is_verified": False}
    
    # 检查是否过期 (3天)
    now = datetime.datetime.utcnow()
    if config.updated_at and (now - config.updated_at).days >= 3:
        # 已过期，删除密钥
        db.delete(config)
        db.commit()
        return {"is_verified": False, "reason": "expired"}
        
    return {"is_verified": True}

@app.post("/api/auth/logout")
async def logout(db: Session = Depends(database.get_db)):
    config = db.query(models.SystemConfig).filter(models.SystemConfig.key == "secret_key").first()
    if config:
        db.delete(config)
        db.commit()
    return {"status": "success"}

@app.post("/api/auth/verify-secret")
async def verify_secret(req: schemas.SecretVerifyRequest, db: Session = Depends(database.get_db)):
    secret_key = req.secret_key
    verify_url = f"http://szgaocheng.cn/api/auth/secret/{secret_key}"
    
    try:
        response = requests.get(verify_url, timeout=10)
        if response.status_code == 200:
            # 验证通过，保存密钥
            config = db.query(models.SystemConfig).filter(models.SystemConfig.key == "secret_key").first()
            if config:
                config.value = secret_key
            else:
                config = models.SystemConfig(key="secret_key", value=secret_key)
                db.add(config)
            db.commit()
            return {"status": "success", "message": "验证通过"}
        elif response.status_code in [401, 403]:
            raise HTTPException(status_code=401, detail="密钥验证不通过，请检查密钥是否正确")
        else:
            raise HTTPException(status_code=response.status_code, detail=f"系统未知错误 (Code: {response.status_code})")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"无法连接验证服务器: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"验证过程出错: {str(e)}")

@app.post("/api/auth/login")
async def login(req: schemas.LoginRequest, db: Session = Depends(database.get_db)):
    try:
        session_id, uid = login_qyb(req.mobile, req.password)
        user = db.query(models.UserSession).filter(models.UserSession.mobile == req.mobile).first()
        if user:
            user.session_id = session_id
            user.uid = uid
        else:
            user = models.UserSession(mobile=req.mobile, session_id=session_id, uid=uid)
            db.add(user)
        db.commit()
        return {"status": "success", "session_id": session_id, "uid": uid}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@app.get("/api/auth/sessions")
async def get_sessions(db: Session = Depends(database.get_db)):
    users = db.query(models.UserSession).all()
    return users

@app.delete("/api/auth/sessions/{mobile}")
async def delete_session(mobile: str, db: Session = Depends(database.get_db)):
    user = db.query(models.UserSession).filter(models.UserSession.mobile == mobile).first()
    if not user:
        raise HTTPException(status_code=404, detail="未找到该授权信息")
    db.delete(user)
    db.commit()
    return {"status": "success"}

@app.post("/api/tasks/parse-excel")
async def parse_excel(file: UploadFile = File(...)):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="仅支持 Excel 文件")
    
    try:
        df = pd.read_excel(file.file)
        # 简单清洗和映射
        tasks = []
        for _, row in df.iterrows():
            if pd.isna(row.get("发送人")) or pd.isna(row.get("智能标签")) or pd.isna(row.get("接收人")):
                continue
            tasks.append({
                "sender": str(row["发送人"]),
                "tag": str(row["智能标签"]),
                "receiver": str(row["接收人"]),
                "internal": "是" in str(row.get("接收人是否为内部员工", "")),
                "start": int(row.get("起始位置", 1)),
                "limit": int(row.get("发送数量", -1))
            })
        print(f"📂 Excel 解析成功: {file.filename}, 共 {len(tasks)} 条任务")
        for idx, t in enumerate(tasks):
            print(f"  [{idx+1}] {t['sender']} -> {t['receiver']} | 起始: {t['start']} | 数量: {t['limit']}")
        return {"filename": file.filename, "tasks": tasks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")

@app.post("/api/tasks/start")
async def start_task(req: schemas.TaskCreate, mobile: str, db: Session = Depends(database.get_db)):
    user = db.query(models.UserSession).filter(models.UserSession.mobile == mobile).first()
    if not user:
        raise HTTPException(status_code=404, detail="未找到该账号的授权信息")
    
    task_id = str(uuid.uuid4())
    task_manager.start_task(task_id, [t.dict() for t in req.tasks], user.session_id, user.uid)
    
    # 存入数据库
    new_task = models.TaskRecord(
        id=task_id,
        filename="Manual Batch", # 实际可动态传入
        status="running",
        log_path=f"tasks/logs/{task_id}.log"
    )
    db.add(new_task)
    db.commit()
    
    return {"task_id": task_id}

@app.post("/api/tasks/{task_id}/stop")
async def stop_task(task_id: str, db: Session = Depends(database.get_db)):
    success = task_manager.stop_task(task_id)
    if success:
        task = db.query(models.TaskRecord).filter(models.TaskRecord.id == task_id).first()
        if task:
            task.status = "stopped"
            db.commit()
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="任务不存在或已结束")

@app.get("/api/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    is_active = task_id in task_manager.active_tasks
    return {"task_id": task_id, "is_active": is_active}

@app.get("/api/tasks")
async def get_tasks(db: Session = Depends(database.get_db)):
    tasks = db.query(models.TaskRecord).order_by(models.TaskRecord.created_at.desc()).all()
    return tasks

@app.get("/api/tasks/{task_id}/logs")
async def get_task_logs(task_id: str):
    log_file_path = f"tasks/logs/{task_id}.log"
    if not os.path.exists(log_file_path):
        return {"logs": []}
    with open(log_file_path, "r", encoding="utf-8") as f:
        return {"logs": f.read().splitlines()}

@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str, db: Session = Depends(database.get_db)):
    task = db.query(models.TaskRecord).filter(models.TaskRecord.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 删除日志文件
    log_file_path = f"tasks/logs/{task_id}.log"
    if os.path.exists(log_file_path):
        os.remove(log_file_path)
    
    db.delete(task)
    db.commit()
    return {"status": "success"}

@app.websocket("/api/ws/logs/{task_id}")
async def websocket_logs(websocket: WebSocket, task_id: str, db: Session = Depends(database.get_db)):
    await websocket.accept()
    if task_id not in task_manager.active_tasks:
        await websocket.send_text("任务未找到或已关闭。")
        await websocket.close()
        return
    
    log_queue = task_manager.active_tasks[task_id]["log_queue"]
    log_dir = "tasks/logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file_path = f"{log_dir}/{task_id}.log"
    
    # 1. 先发送历史日志（如果有）
    if os.path.exists(log_file_path):
        try:
            with open(log_file_path, "r", encoding="utf-8") as f:
                history = f.read()
                if history:
                    for line in history.splitlines():
                        await websocket.send_text(line)
        except Exception as e:
            print(f"Error reading history logs: {e}")

    # 2. 持续监听新日志
    try:
        with open(log_file_path, "a", encoding="utf-8") as f:
            while True:
                # 非阻塞读取队列
                if not log_queue.empty():
                    msg = log_queue.get()
                    if msg is None: # 结束标记
                        await websocket.send_text("--- 任务执行完毕 ---")
                        break
                    
                    f.write(msg + "\n")
                    f.flush()
                    await websocket.send_text(msg)
                else:
                    await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WS Error: {e}")
    finally:
        # 任务结束后清理 active_tasks
        if task_id in task_manager.active_tasks:
            del task_manager.active_tasks[task_id]
        try:
            await websocket.close()
        except:
            pass

import asyncio
