"""
JNM_SPVL Core Protocol Definition v1.0
檔案位置: /shared/protocol.py
功能: 統一全域度量衡，提供物理數據與邏輯標籤的對映表。
"""

class JNMProtocol:
    # --- 時間維度 (Time Dimension) ---
    TICKS_PER_BAR = 1920          # 標準四拍小節總 Tick 數
    QUARTER_NOTE_TICK = 480       # 四分音符
    EIGHTH_NOTE_TICK = 240        # 八分音符
    SIXTEENTH_NOTE_TICK = 120     # 十六分音符

    # --- 音高維度 (Pitch Dimension) ---
    PITCH_MIN = 1                 # 鋼琴最左端 (A0)
    PITCH_MAX = 88                # 鋼琴最右端 (C8)
    MIDI_OFFSET = 20              # 物理轉換公式: MIDI = P + 20

    # --- 力度維度 (Velocity Dimension) ---
    # 將 MIDI 0-127 映射至 V1-V5
    VELOCITY_MAP = {
        1: (25, 44),    # pp (很弱)
        2: (45, 64),    # p  (弱)
        3: (65, 84),    # mf (中強)
        4: (85, 104),   # f  (強)
        5: (105, 125)   # ff (極強)
    }

    # --- 織體風格 ID (Style IDs) ---
    STYLES = {
        "01": "PEDAL_BLOCK",      # 初級：長音柱狀
        "02": "QUARTER_BLOCK",    # 初級：四拍柱狀
        "11": "8TH_ARPEGGIO",     # 中級：八分分解
        "12": "ALBERTI_BASS",     # 中級：艾伯提低音
        "21": "WALKING_BASS",     # 高級：步行貝斯
        "22": "STRIDE_PIANO",     # 高級：大跨度跳躍
        "99": "FREE_IMPROV"       # 特級：全即興
    }

    @staticmethod
    def midi_to_p(midi_pitch: int) -> int:
        """MIDI 音高轉為 JNM P值"""
        p = midi_pitch - 20
        return max(1, min(88, p))

    @staticmethod
    def velocity_to_v(midi_velocity: int) -> int:
        """MIDI 力度轉為 JNM V值"""
        for v, (low, high) in JNMProtocol.VELOCITY_MAP.items():
            if low <= midi_velocity <= high:
                return v
        return 3 if midi_velocity > 0 else 0 # 預設中強
