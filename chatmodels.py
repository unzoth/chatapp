from openai import OpenAI

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