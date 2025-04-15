from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from db import get_db
from models import User, Dialog, ChatRecord
from chatmodels import ask_ai_stream_context  # 支持上下文的流式调用函数（同步生成器）
import hashlib
from typing import Optional, List
from datetime import datetime
import os
import base64
import re
import asyncio
import threading

app = FastAPI()

# CORS 设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载 uploads 文件夹作为静态资源
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ----------------- 全局停止标识 -----------------
# 用于记录每个对话的停止状态，key 为 dialog_id，value 为 bool
STOP_FLAGS = {}

# ----------------- 数据传输模型 -----------------

class NewDialogRequest(BaseModel):
    username: str
    conversation_title: str = "新对话"

class NewDialogResponse(BaseModel):
    dialog_id: int

class QuestionRequest(BaseModel):
    username: str
    dialog_id: Optional[int] = None  # 新对话时不传；继续对话时传入已有 dialog_id
    conversation_title: str = "新对话"
    question: str
    model: str = "model1"  # 可选值："model1"、"model2"、"model3"
    image_base64: Optional[str] = None
    image_path: Optional[str] = None

class RegisterRequest(BaseModel):
    username: str
    password: str

class RegisterResponse(BaseModel):
    message: str
    user_id: int

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    message: str
    user_id: int

class DeleteDialogRequest(BaseModel):
    username: str

class UpdateTitleRequest(BaseModel):
    title: str
    username: str

# ---------------- 新增：对话与聊天记录的响应模型 ----------------
class ChatRecordResponse(BaseModel):
    record_id: int
    content: str
    role: int  # 1 表示用户发送，0 表示 AI 回复
    created_at: datetime
    media_url: Optional[str] = None

class DialogWithRecordsResponse(BaseModel):
    dialog_id: int
    title: str
    chat_records: List[ChatRecordResponse]

class GetDialogsResponse(BaseModel):
    conversations: List[DialogWithRecordsResponse]

# ----------------- 通用函数 -----------------

def save_to_db(db: Session, user: User, dialog: Dialog, question: str, answer: str,
               image_path: Optional[str] = None):
    """
    保存聊天记录：
      - 用户消息保存时，如果 image_path 存在，则存入 media_url，媒体类型设置为 "image"
      - AI 回复仅保存文本内容
    """
    chat_record_user = ChatRecord(
        dialog_id=dialog.dialog_id,
        user_id=user.user_id,
        content=question,
        role=1,
        media_url=image_path,
        media_type="image" if image_path else None
    )
    chat_record_ai = ChatRecord(
        dialog_id=dialog.dialog_id,
        user_id=user.user_id,
        content=answer,
        role=0
    )
    db.add(chat_record_user)
    db.add(chat_record_ai)
    db.commit()

def encode_image(image_path: str) -> str:
    if not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="图片路径不存在")
    with open(image_path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"

def save_image_file(base64_data: str, user_id: int, dialog_id: int, original_filename: str) -> str:
    """
    保存 Base64 编码的图片到本地，返回保存后的相对路径
    """
    pattern = r"^data:image/.+;base64,"
    base64_str = re.sub(pattern, "", base64_data)
    directory = os.path.join("uploads", str(user_id), str(dialog_id))
    os.makedirs(directory, exist_ok=True)
    file_path = os.path.join(directory, original_filename)
    with open(file_path, "wb") as f:
        f.write(base64.b64decode(base64_str))
    relative_path = os.path.join(str(user_id), str(dialog_id), original_filename)
    return relative_path.replace("\\", "/")

# ----------------- 接口实现 -----------------

@app.delete("/dialog/{dialog_id}")
async def delete_dialog(dialog_id: int, username: str, db: Session = Depends(get_db)):
    print(f"[DEBUG] 收到删除请求，dialog_id: {dialog_id}，username: {username}")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    dialog = db.query(Dialog).filter(Dialog.dialog_id == dialog_id, Dialog.user_id == user.user_id).first()
    if not dialog:
        raise HTTPException(status_code=404, detail="对话不存在")
    db.query(ChatRecord).filter(ChatRecord.dialog_id == dialog_id).delete(synchronize_session=False)
    db.delete(dialog)
    db.commit()
    return {"message": "删除成功", "dialog_id": dialog_id}

@app.put("/dialog/{dialog_id}")
async def update_dialog_title(dialog_id: int, request: UpdateTitleRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == request.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    dialog = db.query(Dialog).filter(Dialog.dialog_id == dialog_id, Dialog.user_id == user.user_id).first()
    if not dialog:
        raise HTTPException(status_code=404, detail="对话不存在")
    dialog.title = request.title
    db.commit()
    return {"message": "标题更新成功", "dialog_id": dialog.dialog_id, "title": dialog.title}

@app.post("/new_dialog", response_model=NewDialogResponse)
async def create_new_dialog(request: NewDialogRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == request.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    dialog = Dialog(user_id=user.user_id, title=request.conversation_title)
    db.add(dialog)
    db.commit()
    db.refresh(dialog)
    print(f"[DEBUG] 创建新对话，dialog_id: {dialog.dialog_id}")
    return NewDialogResponse(dialog_id=dialog.dialog_id)

@app.post("/register", response_model=RegisterResponse)
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == request.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")
    hashed_password = hashlib.sha256(request.password.encode()).hexdigest()
    user = User(username=request.username, password_hash=hashed_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return RegisterResponse(message="注册成功", user_id=user.user_id)

@app.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == request.username).first()
    if not user:
        raise HTTPException(status_code=400, detail="账号或密码错误")
    hashed_password = hashlib.sha256(request.password.encode()).hexdigest()
    if user.password_hash != hashed_password:
        raise HTTPException(status_code=400, detail="账号或密码错误")
    return LoginResponse(message="登录成功", user_id=user.user_id)

@app.post("/ask")
async def ask_question_stream(request: QuestionRequest, db: Session = Depends(get_db)):
    """
    流式回复接口，支持外部停止控制：
    将生成的每个回复 chunk 同时发送给前端和累积到 full_response 变量中，
    当收到停止请求时，直接中断回复，将 full_response 保存到数据库，然后结束流式返回。
    """
    if request.dialog_id is None:
        raise HTTPException(status_code=400, detail="请先创建对话，dialog_id 不能为空")
    user = db.query(User).filter(User.username == request.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    dialog = db.query(Dialog).filter(Dialog.dialog_id == request.dialog_id, Dialog.user_id == user.user_id).first()
    if not dialog:
        raise HTTPException(status_code=404, detail="对话不存在")

    # 初始化停止标识（False 表示不中断）
    STOP_FLAGS[dialog.dialog_id] = False

    if request.image_base64 and request.image_path:
        relative_image_path = save_image_file(request.image_base64, user.user_id, dialog.dialog_id, request.image_path)
        request.image_path = relative_image_path

    records = db.query(ChatRecord).filter(ChatRecord.dialog_id == dialog.dialog_id).order_by(ChatRecord.created_at).all()
    messages = [{
        "role": "system",
        "content": "你是一位智能助手，请确保所有回复均采用 Markdown 格式输出。所有数学公式必须使用标准 LaTeX 语法输出：行内公式请使用 `$...$` 包裹；块级公式请使用 `$$...$$` 包裹。"
    }]
    for record in records:
        if record.role == 1:
            messages.append({"role": "user", "content": record.content})
        else:
            messages.append({"role": "assistant", "content": record.content})

    if request.image_base64:
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": request.question},
                {"type": "image_url", "image_url": {"url": request.image_base64}}
            ]
        })
    else:
        messages.append({"role": "user", "content": request.question})

    # 获取 AI 回复同步生成器
    generator = ask_ai_stream_context(messages, request.model)

    # 创建 asyncio.Queue，用于在线程中收集生成的 chunk
    chunk_queue = asyncio.Queue()

    # 用于累积已生成的回复
    full_response = []

    # 定义线程函数，读取生成器，将每个 chunk 放入队列，同时累积到 full_response 中
    def generator_thread():
        try:
            for chunk in generator:
                # 如果收到停止标识，直接退出循环
                if STOP_FLAGS.get(dialog.dialog_id, False):
                    print(f"[DEBUG] 线程检测到停止标识，结束生成，dialog_id: {dialog.dialog_id}")
                    break
                full_response.append(chunk)
                # 将 chunk 放入队列（阻塞放入）
                asyncio.run(chunk_queue.put(chunk))
        except Exception as e:
            print(f"[ERROR] 生成器线程异常: {e}")
        finally:
            # 放入 None 作为结束标记
            asyncio.run(chunk_queue.put(None))

    # 启动线程读取生成器
    thread = threading.Thread(target=generator_thread, daemon=True)
    thread.start()

    async def answer_generator():
        # 从队列中获取 chunk 并 yield 给前端
        response_text = ""
        while True:
            chunk = await chunk_queue.get()
            if chunk is None:
                break
            response_text += chunk
            yield chunk
        # 最终将累积的回复保存到数据库
        save_to_db(db, user, dialog, request.question, "".join(full_response), image_path=request.image_path)
        print(f"[DEBUG] 聊天记录已保存到 dialog_id: {dialog.dialog_id}")

    headers = {"X-Dialog-ID": str(dialog.dialog_id)}
    print(f"[DEBUG] 响应返回，header 中的 dialog_id: {dialog.dialog_id}")
    return StreamingResponse(answer_generator(), media_type="text/plain", headers=headers)

# ---------------- 新增停止接口 ----------------
class StopRequest(BaseModel):
    dialog_id: int
    username: str

@app.post("/stop")
async def stop_reply(request: StopRequest):
    # 收到停止请求时，设置对应对话的停止标识为 True
    STOP_FLAGS[request.dialog_id] = True
    print(f"[DEBUG] 设置对话 {request.dialog_id} 的停止标识为 True")
    return {"message": "停止请求已接收"}

@app.get("/dialogs", response_model=GetDialogsResponse)
async def get_dialogs(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    dialog_data = (
        db.query(Dialog, func.max(ChatRecord.created_at).label("last_user_message"))
        .outerjoin(ChatRecord, (ChatRecord.dialog_id == Dialog.dialog_id) & (ChatRecord.role == 1))
        .filter(Dialog.user_id == user.user_id)
        .group_by(Dialog.dialog_id)
        .order_by(desc(func.max(ChatRecord.created_at)))
        .all()
    )
    conversations = []
    for dialog, _ in dialog_data:
        records = (
            db.query(ChatRecord)
            .filter(ChatRecord.dialog_id == dialog.dialog_id)
            .order_by(ChatRecord.created_at)
            .all()
        )
        conv = {
            "dialog_id": dialog.dialog_id,
            "title": dialog.title,
            "chat_records": [
                {
                    "record_id": record.record_id,
                    "content": record.content,
                    "role": record.role,
                    "created_at": record.created_at,
                    "media_url": record.media_url
                }
                for record in records
            ]
        }
        conversations.append(conv)
    return {"conversations": conversations}

