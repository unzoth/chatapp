"""
聊天路由模块

处理AI对话的问答和流式响应
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import asyncio
import threading
from db import get_db
from chatmodels import ask_ai_stream_context
from models import Dialog, ChatRecord
from schemas import QuestionRequest, StopRequest
from utils import (
    STOP_FLAGS, save_to_db, save_image_file,
    get_user_by_username, get_dialog_by_id, get_chat_history
)
from config import SYSTEM_PROMPT

router = APIRouter(tags=["聊天"])


@router.post("/ask")
async def ask_question_stream(request: QuestionRequest, db: Session = Depends(get_db)):
    """
    流式回复接口，支持外部停止控制

    Args:
        request: 提问请求
        db: 数据库会话

    Returns:
        流式文本响应

    Raises:
        HTTPException: 当对话ID为空、用户不存在或对话不存在时

    Note:
        将生成的每个回复chunk同时发送给前端和累积到full_response变量中，
        当收到停止请求时，直接中断回复，将full_response保存到数据库，然后结束流式返回。
    """
    if request.dialog_id is None:
        raise HTTPException(status_code=400, detail="请先创建对话，dialog_id 不能为空")

    user = get_user_by_username(db, request.username)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    dialog = get_dialog_by_id(db, request.dialog_id, user.user_id)
    if not dialog:
        raise HTTPException(status_code=404, detail="对话不存在")

    # 初始化停止标识（False 表示不中断）
    STOP_FLAGS[dialog.dialog_id] = False

    # 处理图片上传
    if request.image_base64 and request.image_path:
        relative_image_path = save_image_file(
            request.image_base64,
            user.user_id,
            dialog.dialog_id,
            request.image_path
        )
        request.image_path = relative_image_path

    # 获取对话历史
    records = get_chat_history(db, dialog.dialog_id)

    # 构建消息上下文
    messages = [{
        "role": "system",
        "content": SYSTEM_PROMPT
    }]

    # 添加历史消息
    for record in records:
        if record.role == 1:
            messages.append({"role": "user", "content": record.content})
        else:
            messages.append({"role": "assistant", "content": record.content})

    # 添加当前问题（包含可能的图片）
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
        save_to_db(
            db, user, dialog, request.question,
            "".join(full_response), image_path=request.image_path
        )
        print(f"[DEBUG] 聊天记录已保存到 dialog_id: {dialog.dialog_id}")

    headers = {"X-Dialog-ID": str(dialog.dialog_id)}
    print(f"[DEBUG] 响应返回，header 中的 dialog_id: {dialog.dialog_id}")
    return StreamingResponse(answer_generator(), media_type="text/plain", headers=headers)


@router.post("/stop")
async def stop_reply(request: StopRequest):
    """
    停止AI回复生成

    Args:
        request: 停止请求

    Returns:
        停止操作结果
    """
    # 收到停止请求时，设置对应对话的停止标识为 True
    STOP_FLAGS[request.dialog_id] = True
    print(f"[DEBUG] 设置对话 {request.dialog_id} 的停止标识为 True")
    return {"message": "停止请求已接收"}