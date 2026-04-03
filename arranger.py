"""
JNM Arranger Core v1.0
檔案位置: /arranger_ai/arranger.py
功能: 根據 T1 旋律與風格標籤，自動生成 T2 伴奏序列。
"""

from shared.protocol import JNMProtocol

class JNMArranger:
    def __init__(self, style_id="11"): # 預設：八分分解 (8TH_ARPEGGIO)
        self.style_id = style_id
        self.t2_tokens = ["T2"]

    def generate_t2(self, t1_sequence: str) -> str:
        """
        核心編曲邏輯：分析 T1，產出 T2
        """
        # 1. 解析 T1 序列為物件清單
        t1_notes = self._parse_jnm(t1_sequence)
        
        # 2. 以小節 (BAR) 為單位進行處理
        bars = self._split_into_bars(t1_notes)
        
        for bar_notes in bars:
            # 取得該小節的基底和弦 (假設邏輯：取旋律首音或強拍音)
            root_p = self._guess_root_pitch(bar_notes)
            
            # 3. 根據 Style ID 執行織體生成
            if self.style_id == "02": # 四拍柱狀
                self._gen_quarter_block(root_p)
            elif self.style_id == "11": # 八分分解
                self._gen_8th_arpeggio(root_p)
            elif self.style_id == "21": # 步行貝斯
                self._gen_walking_bass(root_p)
                
            self.t2_tokens.append("BAR")
            
        return " | ".join(self.t2_tokens)

    def _gen_8th_arpeggio(self, root_p):
        """生成中級：1-5-8-10 度分解音"""
        # 邏輯：S240 (八分音符) 循環
        pattern = [0, 7, 12, 16] # 半音間距
        for offset in pattern:
            p = root_p + offset
            # 確保 T2 永遠在低音區 (P < 40)
            p = p if p < 40 else p - 12
            self.t2_tokens.append(f"S240_P{p}_V2_L240")

    def _guess_root_pitch(self, bar_notes):
        # 簡化邏輯：抓小節第一個音，降兩個八度作為根音
        if not bar_notes: return 16 # 預設 C1
        return max(1, bar_notes[0]['P'] - 24)

    def _parse_jnm(self, jnm_str):
        # 將字串還原為字典的工具函數...
        pass
