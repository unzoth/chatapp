from openai import OpenAI
from typing import List, Dict, Generator, Tuple

# 初始化 DeepSeek 客户端，请替换为您的实际 API 密钥
client_deepseek = OpenAI(
    api_key="sk-9e012348e427425a8b2bea07c483240d",
    base_url="https://api.deepseek.com/v1",
)

client_baidu = OpenAI(
    api_key="bce-v3/ALTAK-HsyiEU6sdY4aEe4EZJ0O7/b5d9febb8cf89fb62ab7fc53bb06be32645c9ba6",
    base_url="https://qianfan.baidubce.com/v2",
)

client_tongyi = OpenAI(
    api_key="sk-0417401544f241b2a9abd1c2fd74ed6b",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

client_hunyuan = OpenAI(
    api_key="sk-nNzbVtZz0ONsHC8Zy16qtZuhu137n7arPnvgZ3bOAicJmewy",
    base_url="https://api.hunyuan.cloud.tencent.com/v1",
)


def ask_ai_stream_context(messages: List[Dict[str, str]], model: str = "model1") -> Generator[
    Tuple[str, str], None, None]:
    """
    使用带上下文的消息列表调用 API，实现多轮对话。
    messages 为列表，每个元素为 {"role": "user"|"assistant", "content": "文本内容"}。
    返回元组 (content_chunk, reasoning_chunk)，当某个部分没有内容时为空字符串
    """
    if model == "model1":
        response = client_deepseek.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            stream=True
        )
    elif model == "model2":
        response = client_deepseek.chat.completions.create(
            model="deepseek-reasoner",
            messages=messages,
            stream=True
        )
    elif model == "model3":
        response = client_baidu.chat.completions.create(
            model="ernie-4.5-8k-preview",
            messages=messages,
            stream=True
        )
    elif model == "model4":
        response = client_tongyi.chat.completions.create(
            model="qwq-plus",
            messages=messages,
            stream=True
        )
    elif model == "model5":
        response = client_hunyuan.chat.completions.create(
            model="hunyuan-turbos-latest",
            messages=messages,
            stream=True
        )
    elif model == "model6":
        response = client_baidu.chat.completions.create(
            model="ernie-4.5-8k-preview",
            messages=messages,
            stream=True
        )

    for chunk in response:
        delta = chunk.choices[0].delta
        content_chunk = ""
        reasoning_chunk = ""

        # 处理普通内容
        if hasattr(delta, "content") and delta.content:
            content_chunk = delta.content

        # 处理reasoning内容
        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
            reasoning_chunk = delta.reasoning_content

        # 返回元组 (content_chunk, reasoning_chunk)
        yield (content_chunk, reasoning_chunk)