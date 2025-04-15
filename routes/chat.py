"""
聊天路由模块

处理AI对话的问答和流式响应
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
import asyncio
import threading
import json
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

# 用于存储每个对话的推理内容队列
REASONING_QUEUES = {}


@router.post("/ask")
async def ask_question_stream(request: QuestionRequest, db: Session = Depends(get_db)):
    """
    流式回复接口，支持外部停止控制，并包含推理内容

    Args:
        request: 提问请求
        db: 数据库会话

    Returns:
        流式文本响应，包含内容和推理过程

    Raises:
        HTTPException: 当对话ID为空、用户不存在或对话不存在时
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

    # 创建或重置该对话的推理内容队列
    REASONING_QUEUES[dialog.dialog_id] = asyncio.Queue()

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

    # 用于累积已生成的回复和推理内容
    full_response = []
    full_reasoning = []

    # 定义线程函数，读取生成器，将每个 chunk 放入队列，同时累积到 full_response 和 full_reasoning 中
    def generator_thread():
        try:
            for content_chunk, reasoning_chunk in generator:
                # 如果收到停止标识，直接退出循环
                if STOP_FLAGS.get(dialog.dialog_id, False):
                    print(f"[DEBUG] 线程检测到停止标识，结束生成，dialog_id: {dialog.dialog_id}")
                    break

                # 处理内容和推理
                if content_chunk:
                    full_response.append(content_chunk)

                if reasoning_chunk:
                    full_reasoning.append(reasoning_chunk)
                    # 将推理内容放入对应的推理队列，用于流式输出推理内容
                    asyncio.run(REASONING_QUEUES[dialog.dialog_id].put(reasoning_chunk))

                # 将 chunk 放入队列（阻塞放入）- 只传入内容部分
                asyncio.run(chunk_queue.put(content_chunk))
        except Exception as e:
            print(f"[ERROR] 生成器线程异常: {e}")
        finally:
            # 放入 None 作为结束标记
            asyncio.run(chunk_queue.put(None))
            # 向推理队列也发送结束信号
            if dialog.dialog_id in REASONING_QUEUES:
                asyncio.run(REASONING_QUEUES[dialog.dialog_id].put(None))

        # 启动线程读取生成器

    thread = threading.Thread(target=generator_thread, daemon=True)
    thread.start()

    async def answer_generator():
        # 从队列中获取 chunk 并 yield 给前端
        response_text = ""
        while True:
            content_chunk = await chunk_queue.get()
            if content_chunk is None:
                break
            if content_chunk:  # 避免发送空字符串
                response_text += content_chunk
                yield content_chunk
        # 最终将累积的回复和推理内容保存到数据库
        save_to_db(
            db, user, dialog, request.question,
            "".join(full_response),
            reasoning_content="".join(full_reasoning),
            image_path=request.image_path
        )
        print(f"[DEBUG] 聊天记录已保存到 dialog_id: {dialog.dialog_id}")

    headers = {
        "X-Dialog-ID": str(dialog.dialog_id),
        "X-Has-Reasoning": "true" if request.model == "model2" or request.model == "deepseek-reasoner" else "false"
    }
    print(f"[DEBUG] 响应返回，header 中的 dialog_id: {dialog.dialog_id}")
    return StreamingResponse(answer_generator(), media_type="text/plain", headers=headers)


@router.get("/reasoning/{dialog_id}")
async def get_reasoning_content(dialog_id: int, db: Session = Depends(get_db)):
    """
    获取最新消息的推理内容

    Args:
        dialog_id: 对话ID
        db: 数据库会话

    Returns:
        推理内容
    """
    # 获取对话中最新的AI回复记录
    latest_record = (
        db.query(ChatRecord)
        .filter(ChatRecord.dialog_id == dialog_id, ChatRecord.role == 2)  # 2 表示AI
        .order_by(desc(ChatRecord.created_at))
        .first()
    )

    if not latest_record:
        raise HTTPException(status_code=404, detail="未找到AI回复记录")

    return {"reasoning_content": latest_record.reasoning_content or ""}


@router.get("/reasoning/stream/{dialog_id}")
async def stream_reasoning_content(dialog_id: int):
    """
    流式获取推理内容

    Args:
        dialog_id: 对话ID

    Returns:
        推理内容的流式响应
    """
    # 检查是否有该对话的推理队列
    if dialog_id not in REASONING_QUEUES:
        REASONING_QUEUES[dialog_id] = asyncio.Queue()  # 如果不存在就创建一个空队列

    queue = REASONING_QUEUES[dialog_id]

    async def reasoning_generator():
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:  # 结束信号
                    yield "event: complete\ndata: complete\n\n"
                    break
                yield f"event: message\ndata: {chunk}\n\n"
        except asyncio.CancelledError:
            print(f"[DEBUG] 推理内容流被取消，dialog_id: {dialog_id}")
        finally:
            print(f"[DEBUG] 推理内容流结束，dialog_id: {dialog_id}")

    return StreamingResponse(
        reasoning_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


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

    # 清理该对话的推理队列
    if request.dialog_id in REASONING_QUEUES:
        try:
            # 尝试向队列添加结束信号
            asyncio.run(REASONING_QUEUES[request.dialog_id].put(None))
        except:
            pass

    return {"message": "停止请求已接收"}


# 在应用结束时清理资源的函数，可以在FastAPI的startup/shutdown事件中调用
def cleanup_reasoning_queues():
    """清理所有推理队列"""
    for dialog_id in list(REASONING_QUEUES.keys()):
        try:
            asyncio.run(REASONING_QUEUES[dialog_id].put(None))
        except:
            pass
        REASONING_QUEUES.pop(dialog_id, None)