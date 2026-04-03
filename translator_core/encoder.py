import json
from shared.protocol import JNMProtocol

class JNMEncoder:
    def __init__(self, bpm=120):
        self.bpm = bpm
        self.tick_factor = (bpm / 60) * JNMProtocol.QUARTER_NOTE_TICK
        self.current_total_ticks = 0

    def _to_ticks(self, seconds: float) -> int:
        """將秒數轉換為最接近的 10 Tick 倍數（初步磁吸）"""
        raw_ticks = int(seconds * self.tick_factor)
        return round(raw_ticks / 10) * 10

    def process_to_t1(self, raw_notes: list) -> str:
        """
        將原始 MIDI 事件清單轉換為 JNM_SPVL T1 旋律字串
        raw_notes 格式範例: [{'start': 1.2, 'end': 1.5, 'pitch': 60, 'velocity': 80}, ...]
        """
        # 1. 依照開始時間排序
        sorted_notes = sorted(raw_notes, key=lambda x: x['start'])
        
        jnm_tokens = ["T1"]
        last_onset_tick = 0
        bar_accumulator = 0

        # 2. 最高音過濾 (去骨邏輯)
        # 如果多個音符起始時間極近（< 50 Ticks），視為和弦，只取最高音
        filtered_notes = []
        if sorted_notes:
            current_group = [sorted_notes[0]]
            for i in range(1, len(sorted_notes)):
                if (self._to_ticks(sorted_notes[i]['start']) - 
                    self._to_ticks(current_group[0]['start'])) < 50:
                    current_group.append(sorted_notes[i])
                else:
                    filtered_notes.append(max(current_group, key=lambda x: x['pitch']))
                    current_group = [sorted_notes[i]]
            filtered_notes.append(max(current_group, key=lambda x: x['pitch']))

        # 3. 轉譯為 JNM 序列
        for note in filtered_notes:
            start_tick = self._to_ticks(note['start'])
            end_tick = self._to_ticks(note['end'])
            
            # 計算 S (與前一個音符的距離)
            s_value = start_tick - last_onset_tick
            p_value = JNMProtocol.midi_to_p(note['pitch'])
            v_value = JNMProtocol.velocity_to_v(note['velocity'])
            l_value = end_tick - start_tick

            # 4. 小節線自動檢查 (BAR)
            bar_accumulator += s_value
            if bar_accumulator >= JNMProtocol.TICKS_PER_BAR:
                jnm_tokens.append("BAR")
                bar_accumulator %= JNMProtocol.TICKS_PER_BAR

            # 5. 封裝 Token
            token = f"S{s_value}_P{p_value}_V{v_value}_L{l_value}"
            jnm_tokens.append(token)
            
            last_onset_tick = start_tick

        return " | ".join(jnm_tokens)

# 使用測試
# encoder = JNMEncoder(bpm=120)
# print(encoder.process_to_t1(raw_data_from_ai))
