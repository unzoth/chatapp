"""
聊天路由模块

处理AI对话的问答和流式响应
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import asyncio
import threading
import json
from db import get_db
from chatmodels import (
    client_deepseek, client_baidu,client_tongyi,client_hunyuan
)
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
    流式回复接口
    """
    if request.dialog_id is None:
        raise HTTPException(status_code=400, detail="请先创建对话，dialog_id 不能为空")

    user = get_user_by_username(db, request.username)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    dialog = get_dialog_by_id(db, request.dialog_id, user.user_id)
    if not dialog:
        raise HTTPException(status_code=404, detail="对话不存在")

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

    # 创建直接流式响应
    return StreamingResponse(
        stream_response(db, user, dialog, request, messages),
        media_type="text/event-stream"
    )


async def stream_response(db, user, dialog, request, messages):
    """直接流式生成响应"""
    # 累积完整回复
    full_answer = ""
    full_reasoning = ""

    # 发送初始化消息
    yield json.dumps({
        "type": "init",
        "content": "开始流式响应"
    }, ensure_ascii=False) + "\n"

    # 获取模型响应
    if request.model == "model1":
        response = client_deepseek.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            stream=True
        )
    elif request.model == "model2":
        response = client_deepseek.chat.completions.create(
            model="deepseek-reasoner",
            messages=messages,
            stream=True
        )
    elif request.model == "model3":
        response = client_baidu.chat.completions.create(
            model="ernie-4.5-8k-preview",
            messages=messages,
            stream=True
        )
    elif request.model == "model4":
        response = client_tongyi.chat.completions.create(
            model="qwq-plus",
            messages=messages,
            stream=True
        )
    elif request.model == "model5":
        response = client_hunyuan.chat.completions.create(
            model="hunyuan-turbos-latest",
            messages=messages,
            stream=True
        )
    elif request.model == "model6":
        response = client_baidu.chat.completions.create(
            model="ernie-4.5-8k-preview",
            messages=messages,
            stream=True
        )

    # 处理流式响应
    try:
        for chunk in response:
            delta = chunk.choices[0].delta
            content_chunk = ""
            reasoning_chunk = ""

            # 处理普通内容
            if hasattr(delta, "content") and delta.content:
                content_chunk = delta.content
                full_answer += content_chunk

            # 处理reasoning内容
            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                reasoning_chunk = delta.reasoning_content
                full_reasoning += reasoning_chunk

            # 按照模型类型构造并发送 JSON 消息
            if request.model == "model2":
                if reasoning_chunk:
                    data = json.dumps({
                        "type": "reasoning",
                        "content": reasoning_chunk
                    }, ensure_ascii=False)
                    yield data + "\n"

                if content_chunk:
                    data = json.dumps({
                        "type": "answer",
                        "content": content_chunk
                    }, ensure_ascii=False)
                    yield data + "\n"
            else:
                if content_chunk:
                    data = json.dumps({
                        "type": "answer",
                        "content": content_chunk
                    }, ensure_ascii=False)
                    yield data + "\n"
    except Exception as e:
        print(f"[ERROR] 流式响应生成错误: {e}")
        yield json.dumps({
            "type": "error",
            "message": f"生成过程中发生错误: {str(e)}"
        }, ensure_ascii=False) + "\n"

    # 发送完成信号
    yield json.dumps({
        "type": "complete",
        "reasoning_total": full_reasoning if request.model == "model2" else "",
        "answer_total": full_answer
    }, ensure_ascii=False) + "\n"

    # 保存到数据库
    try:
        save_to_db(
            db, user, dialog, request.question,
            full_answer,
            image_path=request.image_path,reasoning_content=full_reasoning
        )
        print(f"[DEBUG] 聊天记录已保存至 dialog_id: {dialog.dialog_id}")
    except Exception as e:
        print(f"[ERROR] 保存聊天记录失败: {e}")


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