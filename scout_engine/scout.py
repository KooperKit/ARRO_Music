"""
JNM Scout Pro v1.0
檔案位置: /scout_engine/scout.py
功能: 執行權重搜尋並透過 Vision API 提取樂理元數據 (Metadata)。
"""

import os
import requests
from openai import OpenAI

class JNMScout:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.firecrawl_key = os.getenv("FIRECRAWL_API_KEY")

    def get_vision_truth(self, song_name: str) -> dict:
        """核心流程：搜尋圖片 -> AI 讀圖 -> 產出樂理參數"""
        # 1. 執行階層搜尋 (簡化版邏輯)
        image_url = self._search_highest_quality_image(song_name)
        
        if not image_url:
            return {"confidence": 0, "key": "C_MAJ", "ts": "4/4"}

        # 2. 讓 GPT-4o-mini 讀圖
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "分析這張樂譜，只回傳 JSON：{'key': '調號', 'ts': '拍號', 'confidence': 1-5}"},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ],
                }
            ],
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content

    def _search_highest_quality_image(self, song_name):
        # 這裡調用你之前的 Firecrawl 邏輯
        # 優先找 Level 1 (Official) -> Level 4 (General)
        return "https://example.com/sheet_music.png"
