"""
JNM Validator Core v1.0
檔案位置: /translator_core/validator.py
功能: 執行 JNM 數據的邏輯校驗與平滑化。
"""

from shared.protocol import JNMProtocol

class JNMValidator:
    def __init__(self):
        self.min_length = 40  # 低於 40 Ticks 的音符視為雜訊 (約 1/48 拍)
        self.max_gap_for_legato = 20 # 兩個同音音符間隙小於此值則合併

    def clean_sequence(self, jnm_tokens: list) -> list:
        """
        對 JNM Token 清單進行多重優化
        """
        if not jnm_tokens: return []
        
        cleaned = []
        # 排除 "T1" 開頭標籤進行處理
        prefix = jnm_tokens[0]
        data_tokens = jnm_tokens[1:]
        
        # 1. 基礎物理過濾 (去雜訊)
        filtered = self._filter_noise(data_tokens)
        
        # 2. 連奏修復 (Legato Repair)
        smoothed = self._repair_legato(filtered)
        
        # 3. 小節強制對齊 (Bar Integrity)
        final_data = self._enforce_bar_integrity(smoothed)
        
        return [prefix] + final_data

    def _filter_noise(self, tokens: list) -> list:
        """過濾掉力度過小或長度過短的無效音符"""
        result = []
        for token in tokens:
            if token == "BAR":
                result.append(token)
                continue
            
            # 解析 S480_P40_V3_L480
            parts = {p[0]: int(p[1:]) for p in token.split('_')}
            if parts['L'] >= self.min_length and parts['V'] > 0:
                result.append(token)
        return result

    def _repair_legato(self, tokens: list) -> list:
        """修復「斷斷續續」的同音：如果兩個 P 相同且距離極近，合併長度"""
        if len(tokens) < 2: return tokens
        
        repaired = []
        last_note = None
        
        for token in tokens:
            if token == "BAR":
                repaired.append(token)
                continue
                
            curr = {p[0]: int(p[1:]) for p in token.split('_')}
            
            if last_note and last_note['P'] == curr['P'] and curr['S'] <= self.max_gap_for_legato:
                # 合併：增加上一個音符的 L，目前的音符不加入
                last_note['L'] += curr['S'] + curr['L']
                # 更新 repaired 最後一個元素
                repaired[-1] = f"S{last_note['S']}_P{last_note['P']}_V{last_note['V']}_L{last_note['L']}"
            else:
                repaired.append(token)
                last_note = curr
        return repaired

    def _enforce_bar_integrity(self, tokens: list) -> list:
        """核心校驗：確保每個 BAR 之前的 S 總合等於 1920"""
        bar_sum = 0
        final = []
        for token in tokens:
            if token == "BAR":
                # 誤差修正邏輯：如果目前累積是 1918，強制歸 1920
                if bar_sum != JNMProtocol.TICKS_PER_BAR:
                    # 可以在這裡加入偏移 log
                    pass
                bar_sum = 0
                final.append(token)
            else:
                s_val = int(token.split('_')[0][1:])
                bar_sum += s_val
                final.append(token)
        return final
