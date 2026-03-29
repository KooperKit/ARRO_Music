#!/usr/bin/env python3
"""
禪奈資工二部 — 琴譜構造器
核心轉譜腳本 transcribe.py

執行環境需求（Zeabur Docker 同機安裝）：
  pip install yt-dlp basic-pitch music21 pretty_midi
  apt-get install -y musescore3 ffmpeg

用法：
  python3 transcribe.py --task-id abc123 --url "https://youtube.com/..." \
    --key C --difficulty intermediate \
    --fingering 1 --chord 1 --pedal 0 --tempo 0 --simplify-left 0
"""

import argparse
import json
import os
import sys
import time
import subprocess
import tempfile
import shutil
from pathlib import Path

# ── 路徑設定 ──────────────────────────────────────────────
OUTPUT_DIR = Path("/app/output")
TEMP_DIR   = Path("/tmp/score_tmp")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ── 調性對照表（移調半音數） ──────────────────────────────
KEY_SEMITONES = {
    "C": 0, "D": 2, "E": 4, "F": 5,
    "G": 7, "A": 9, "B": 11, "Bb": 10,
    "Am": 0, "Dm": 2, "Em": 4, "Gm": 7
}

DIFFICULTY_MAP = {
    "beginner":     {"remove_octaves": True,  "simplify_chords": True,  "max_voices": 1},
    "intermediate": {"remove_octaves": False, "simplify_chords": True,  "max_voices": 2},
    "advanced":     {"remove_octaves": False, "simplify_chords": False, "max_voices": 4}
}


def log(msg: str):
    """輸出 stderr log（不影響 stdout JSON）"""
    print(f"[SCORE] {msg}", file=sys.stderr, flush=True)


# ─────────────────────────────────────────────────────────
# STEP 1：下載音源
# ─────────────────────────────────────────────────────────
def download_audio(url: str, task_dir: Path) -> tuple[Path, str]:
    log(f"下載音源：{url}")
    wav_path = task_dir / "source.wav"

    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "wav",
        "--audio-quality", "0",
        "--output", str(task_dir / "source.%(ext)s"),
        "--no-playlist",
        "--max-filesize", "50m",
        url
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(f"音源下載失敗: {result.stderr}")

    # 取得影片標題
    info_cmd = ["yt-dlp", "--get-title", "--no-playlist", url]
    title_result = subprocess.run(info_cmd, capture_output=True, text=True, timeout=30)
    song_title = title_result.stdout.strip() or "未知曲目"

    # yt-dlp 可能輸出 .wav 直接，也可能是其他格式再轉
    if not wav_path.exists():
        # 尋找其他音頻格式並轉換
        for ext in ["mp3", "m4a", "opus", "webm"]:
            src = task_dir / f"source.{ext}"
            if src.exists():
                subprocess.run(
                    ["ffmpeg", "-i", str(src), "-ar", "22050", "-ac", "1", str(wav_path)],
                    capture_output=True, check=True
                )
                src.unlink()
                break

    if not wav_path.exists():
        raise RuntimeError("音頻轉換失敗，找不到輸出檔案")

    log(f"下載完成：{song_title}，檔案大小：{wav_path.stat().st_size // 1024}KB")
    return wav_path, song_title


# ─────────────────────────────────────────────────────────
# STEP 2：AI 轉譜（Basic-Pitch）
# ─────────────────────────────────────────────────────────
def transcribe_audio(wav_path: Path, task_dir: Path) -> Path:
    log("Basic-Pitch AI 轉譜中...")
    from basic_pitch.inference import predict_and_save
    from basic_pitch import ICASSP_2022_MODEL_PATH

    midi_dir = task_dir / "midi_out"
    midi_dir.mkdir(exist_ok=True)

    predict_and_save(
        [str(wav_path)],
        str(midi_dir),
        save_midi=True,
        sonify_midi=False,
        save_model_outputs=False,
        save_notes=False,
        model_or_model_path=ICASSP_2022_MODEL_PATH,
        minimum_frequency=27.5,   # A0 最低鋼琴鍵
        maximum_frequency=4186.0  # C8 最高鋼琴鍵
    )

    midi_files = list(midi_dir.glob("*.mid")) + list(midi_dir.glob("*.midi"))
    if not midi_files:
        raise RuntimeError("Basic-Pitch 未輸出 MIDI 檔案")

    midi_path = midi_files[0]
    log(f"轉譜完成：{midi_path.name}")
    return midi_path


# ─────────────────────────────────────────────────────────
# STEP 3：MIDI → MusicXML（music21）並套用客製化參數
# ─────────────────────────────────────────────────────────
def process_score(
    midi_path: Path,
    task_dir: Path,
    target_key: str,
    difficulty: str,
    add_fingering: bool,
    add_chord: bool,
    add_pedal: bool,
    add_tempo: bool,
    simplify_left: bool
) -> tuple[Path, int, float]:
    log(f"music21 處理：調性={target_key}，難度={difficulty}")

    import music21
    from music21 import (
        converter, stream, note, chord as m21chord,
        key as m21key, tempo, expressions, layout,
        instrument, midi as m21midi
    )

    # 載入 MIDI
    score = converter.parse(str(midi_path))

    # ── 移調 ──────────────────────────────────────────────
    detected_key = score.analyze('key')
    source_key_name = detected_key.tonic.name
    target_semitones = KEY_SEMITONES.get(target_key, 0)
    source_semitones = KEY_SEMITONES.get(source_key_name, 0)
    transpose_interval = target_semitones - source_semitones

    if transpose_interval != 0:
        from music21 import interval
        score = score.transpose(interval.Interval(transpose_interval))
        log(f"移調：{source_key_name} → {target_key}（{transpose_interval:+d} 半音）")

    # ── 難度處理 ──────────────────────────────────────────
    diff_config = DIFFICULTY_MAP[difficulty]
    processed_score = stream.Score()
    processed_score.insert(0, m21key.Key(target_key.rstrip('m'), 'minor' if target_key.endswith('m') else 'major'))

    # 分離高低音部
    parts = list(score.parts)
    if len(parts) == 0:
        raise RuntimeError("score 中沒有音軌")

    # 取第一軌作為旋律，嘗試分割高低音
    if len(parts) == 1:
        all_notes = []
        for element in parts[0].flatten().notes:
            if hasattr(element, 'pitch'):
                all_notes.append((element.offset, element.quarterLength, [element.pitch], element.volume.velocity or 64))
            else:  # chord
                all_notes.append((element.offset, element.quarterLength, list(element.pitches), element.volume.velocity or 64))

        # 依音高分割：C4（MIDI 60）以上為高音部，以下為低音部
        treble_notes = [(o, d, [p for p in pitches if p.midi >= 60], v) for o, d, pitches, v in all_notes if any(p.midi >= 60 for p in pitches)]
        bass_notes   = [(o, d, [p for p in pitches if p.midi < 60],  v) for o, d, pitches, v in all_notes if any(p.midi < 60 for p in pitches)]
    else:
        # 多軌：取前兩軌
        def extract_notes(part):
            result = []
            for element in part.flatten().notes:
                if hasattr(element, 'pitch'):
                    result.append((element.offset, element.quarterLength, [element.pitch], element.volume.velocity or 64))
                else:
                    result.append((element.offset, element.quarterLength, list(element.pitches), element.volume.velocity or 64))
            return result
        treble_notes = extract_notes(parts[0])
        bass_notes = extract_notes(parts[1]) if len(parts) > 1 else []

    # ── 建立高音部 ────────────────────────────────────────
    treble_part = stream.Part()
    treble_part.insert(0, instrument.Piano())
    treble_clef = music21.clef.TrebleClef()
    treble_part.insert(0, treble_clef)

    for offset, duration, pitches, velocity in treble_notes:
        if not pitches:
            continue

        if diff_config["remove_octaves"]:
            # 初級：只保留最高音
            pitches = [max(pitches, key=lambda p: p.midi)]

        if diff_config["max_voices"] == 1:
            n = note.Note(pitches[0])
            n.quarterLength = duration
            if add_fingering:
                _add_fingering(n, offset)
            treble_part.insert(offset, n)
        else:
            if len(pitches) == 1:
                n = note.Note(pitches[0])
                n.quarterLength = duration
                if add_fingering:
                    _add_fingering(n, offset)
                treble_part.insert(offset, n)
            else:
                c = m21chord.Chord(pitches[:diff_config["max_voices"]])
                c.quarterLength = duration
                if add_chord:
                    _add_chord_symbol(c, offset, treble_part)
                treble_part.insert(offset, c)

    # ── 建立低音部 ────────────────────────────────────────
    bass_part = stream.Part()
    bass_part.insert(0, instrument.Piano())
    bass_clef = music21.clef.BassClef()
    bass_part.insert(0, bass_clef)

    for offset, duration, pitches, velocity in bass_notes:
        if not pitches:
            continue

        if simplify_left:
            # 只保留根音（最低音）
            root = min(pitches, key=lambda p: p.midi)
            n = note.Note(root)
            n.quarterLength = max(duration, 1.0)  # 左手延長音
            bass_part.insert(offset, n)
        elif diff_config["simplify_chords"]:
            # 保留根音+五度
            root = min(pitches, key=lambda p: p.midi)
            kept = [p for p in pitches if abs(p.midi - root.midi) in [0, 7, 12]][:2]
            if not kept:
                kept = [root]
            if len(kept) == 1:
                n = note.Note(kept[0])
                n.quarterLength = duration
                bass_part.insert(offset, n)
            else:
                c = m21chord.Chord(kept)
                c.quarterLength = duration
                bass_part.insert(offset, c)
        else:
            if len(pitches) == 1:
                n = note.Note(pitches[0])
                n.quarterLength = duration
                bass_part.insert(offset, n)
            else:
                c = m21chord.Chord(pitches)
                c.quarterLength = duration
                bass_part.insert(offset, c)

    # ── 速度標記 ──────────────────────────────────────────
    if add_tempo:
        # 從原始 MIDI 偵測 BPM
        try:
            detected_bpm = _detect_bpm(midi_path)
        except:
            detected_bpm = 120
        mm = tempo.MetronomeMark(number=detected_bpm)
        treble_part.insert(0, mm)
        log(f"偵測 BPM：{detected_bpm}")
    else:
        detected_bpm = 120

    # ── 踏板記號 ──────────────────────────────────────────
    if add_pedal:
        _add_pedal_marks(bass_part)

    processed_score.append(treble_part)
    processed_score.append(bass_part)

    # 輸出 MusicXML
    xml_path = task_dir / "score.xml"
    processed_score.write('musicxml', fp=str(xml_path))
    log(f"MusicXML 輸出完成：{xml_path}")

    # 計算頁數（粗估）
    total_measures = max(
        len(list(treble_part.getElementsByClass('Measure'))),
        len(list(bass_part.getElementsByClass('Measure')))
    )
    pages = max(1, total_measures // 16)

    return xml_path, pages, detected_bpm


def _add_fingering(note_obj, offset):
    """添加建議指法（基於音符位置的啟發式規則）"""
    from music21 import articulations
    midi = note_obj.pitch.midi % 12
    # 簡單規則：根據音高映射到常見指法
    fingering_map = {0:1, 2:2, 4:3, 5:1, 7:2, 9:3, 11:4}
    finger = fingering_map.get(midi, 3)
    note_obj.articulations.append(articulations.Fingering(finger))


def _add_chord_symbol(chord_obj, offset, part):
    """添加和弦名稱標記"""
    from music21 import harmony
    try:
        chord_name = chord_obj.commonName
        if chord_name:
            cs = harmony.ChordSymbol(chord_name)
            cs.offset = offset
            part.insert(offset, cs)
    except:
        pass


def _add_pedal_marks(part):
    """在每小節開頭添加踏板記號"""
    from music21 import expressions
    measures = list(part.getElementsByClass('Measure'))
    for i, measure in enumerate(measures):
        if i % 2 == 0:  # 每兩小節踩一次
            ped = expressions.TextExpression('Ped.')
            ped.style.absoluteX = 0
            measure.insert(0, ped)
        if i % 2 == 1:
            rel = expressions.TextExpression('*')
            measure.insert(0, rel)


def _detect_bpm(midi_path: Path) -> int:
    """從 MIDI 偵測 BPM"""
    import pretty_midi
    pm = pretty_midi.PrettyMIDI(str(midi_path))
    tempo_changes = pm.get_tempo_changes()
    if len(tempo_changes[1]) > 0:
        return int(tempo_changes[1][0])
    return 120


# ─────────────────────────────────────────────────────────
# STEP 4：MusicXML → PDF（MuseScore CLI）
# ─────────────────────────────────────────────────────────
def export_pdf(xml_path: Path, output_path: Path):
    log(f"MuseScore 排版輸出 PDF：{output_path.name}")

    # MuseScore 3 CLI
    cmd = [
        "mscore3", "-o", str(output_path), str(xml_path)
    ]

    # 若 mscore3 不存在，嘗試 musescore
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"MuseScore 失敗: {result.stderr}")
    except FileNotFoundError:
        cmd[0] = "musescore"
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"musescore 失敗: {result.stderr}")

    if not output_path.exists():
        raise RuntimeError("PDF 未輸出")

    log(f"PDF 輸出完成：{output_path.stat().st_size // 1024}KB")


# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='琴譜構造器 — 核心轉譜腳本')
    parser.add_argument('--task-id',       required=True)
    parser.add_argument('--url',           required=True)
    parser.add_argument('--key',           default='C')
    parser.add_argument('--difficulty',    default='intermediate',
                        choices=['beginner', 'intermediate', 'advanced'])
    parser.add_argument('--fingering',     type=int, default=1)
    parser.add_argument('--chord',         type=int, default=1)
    parser.add_argument('--pedal',         type=int, default=0)
    parser.add_argument('--tempo',         type=int, default=0)
    parser.add_argument('--simplify-left', type=int, default=0)
    args = parser.parse_args()

    start_time = time.time()
    task_dir = TEMP_DIR / args.task_id
    task_dir.mkdir(exist_ok=True)

    try:
        # Step 1
        wav_path, song_title = download_audio(args.url, task_dir)

        # Step 2
        midi_path = transcribe_audio(wav_path, task_dir)

        # Step 3
        xml_path, pages, detected_bpm = process_score(
            midi_path, task_dir,
            target_key=args.key,
            difficulty=args.difficulty,
            add_fingering=bool(args.fingering),
            add_chord=bool(args.chord),
            add_pedal=bool(args.pedal),
            add_tempo=bool(args.tempo),
            simplify_left=bool(args.simplify_left)
        )

        # Step 4
        safe_title = "".join(c for c in song_title if c.isalnum() or c in " _-")[:30]
        pdf_filename = f"{args.task_id}_{safe_title}_{args.key}_{args.difficulty}.pdf"
        pdf_path = OUTPUT_DIR / pdf_filename
        export_pdf(xml_path, pdf_path)

        generation_time = round(time.time() - start_time, 1)

        # 輸出結果 JSON（n8n 讀取）
        result = {
            "success": True,
            "task_id": args.task_id,
            "pdf_path": str(pdf_path),
            "filename": pdf_filename,
            "pages": pages,
            "generation_time": generation_time,
            "song_title": song_title,
            "detected_bpm": detected_bpm,
            "key": args.key,
            "difficulty": args.difficulty
        }
        print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        log(f"錯誤：{e}")
        error_result = {
            "success": False,
            "task_id": args.task_id,
            "error": str(e)
        }
        print(json.dumps(error_result, ensure_ascii=False))
        sys.exit(1)

    finally:
        # 清理暫存（保留 24 小時後刪除由排程處理）
        try:
            shutil.rmtree(task_dir)
        except:
            pass


if __name__ == "__main__":
    main()
