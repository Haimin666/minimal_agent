"""向量嵌入 - 支持多种 API 提供商"""

from typing import List, Optional
import requests


class EmbeddingProvider:
    """
    向量嵌入提供者

    支持:
    - OpenAI API
    - MoArk API (bge-m3)
    - 兼容 OpenAI 格式的其他 API (智谱、阿里云等)
    """

    def __init__(
        self,
        model: str = "bge-m3",
        api_key: str = None,
        api_base: str = "https://api.moark.com/v1",
        dimensions: int = 1024
    ):
        self.model = model
        self.api_key = api_key
        self.api_base = api_base
        self._dimensions = dimensions

    def embed(self, text: str) -> List[float]:
        """生成单个文本的向量"""
        result = self._call_api([text])
        return result[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量生成向量"""
        return self._call_api(texts)

    def _call_api(self, input_data: List[str]) -> List[List[float]]:
        """调用 OpenAI 兼容 API"""
        # 构建请求体
        payload = {
            "input": input_data,
            "model": self.model
        }

        # bge-m3 支持指定维度
        if self._dimensions and "bge" in self.model.lower():
            payload["dimensions"] = self._dimensions

        # 构建请求头
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        # MoArk 需要额外的 header
        if "moark" in self.api_base.lower():
            headers["X-Failover-Enabled"] = "true"

        print(f"[Embedding] 调用 {self.api_base}/embeddings, model={self.model}, texts={len(input_data)}条")

        response = requests.post(
            f"{self.api_base}/embeddings",
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code != 200:
            print(f"[Embedding] 错误: {response.status_code} - {response.text}")
            response.raise_for_status()

        data = response.json()
        embeddings = [item["embedding"] for item in data["data"]]

        print(f"[Embedding] 成功获取 {len(embeddings)} 个向量，维度={len(embeddings[0])}")
        return embeddings

    @property
    def dimensions(self) -> int:
        return self._dimensions
