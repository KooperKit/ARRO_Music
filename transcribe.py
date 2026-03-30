#!/usr/bin/env python3
"""
禪奈資工二部 — 琴譜構造器
transcribe.py v2.1
"""

import argparse
import json
import os
import sys
import time
import subprocess
import shutil
from pathlib import Path

OUTPUT_DIR = Path("/app/output")
TEMP_DIR   = Path("/tmp/score_tmp")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

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

def log(msg):
    print(f"[SCORE] {msg}", file=sys.stderr, flush=True)

# ── STEP 1：下載音源 ──────────────────────────────────────
def download_audio(url, task_dir):
    log(f"下載音源：{url}")
    wav_path = task_dir / "source.wav"

    # 直接 MP3/WAV 連結
    if url.endswith('.mp3') or url.endswith('.wav') or 'soundhelix' in url:
        result = subprocess.run(
            ["curl", "-L", "-o", str(task_dir / "source.mp3"), url],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            raise RuntimeError(f"下載失敗: {result.stderr}")
        src = task_dir / "source.mp3"
        subprocess.run(
            ["ffmpeg", "-i", str(src), "-ar", "22050", "-ac", "1", str(wav_path), "-y"],
            capture_output=True, check=True
        )
        song_title = "測試音源"
    else:
        # YouTube
        cmd = [
            "yt-dlp", "--extract-audio", "--audio-format", "wav",
            "--audio-quality", "0",
            "--output", str(task_dir / "source.%(ext)s"),
            "--no-playlist", "--max-filesize", "50m", url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"音源下載失敗: {result.stderr}")

        info_cmd = ["yt-dlp", "--get-title", "--no-playlist", url]
        title_result = subprocess.run(info_cmd, capture_output=True, text=True, timeout=30)
        song_title = title_result.stdout.strip() or "未知曲目"

        if not wav_path.exists():
            for ext in ["mp3", "m4a", "opus", "webm"]:
                src = task_dir / f"source.{ext}"
                if src.exists():
                    subprocess.run(
                        ["ffmpeg", "-i", str(src), "-ar", "22050", "-ac", "1", str(wav_path), "-y"],
                        capture_output=True, check=True
                    )
                    src.unlink()
                    break

    if not wav_path.exists():
        raise RuntimeError("音頻轉換失敗")

    log(f"下載完成：{song_title}，{wav_path.stat().st_size // 1024}KB")
    return wav_path, song_title

# ── STEP 2：AI 轉譜 ───────────────────────────────────────
def transcribe_audio(wav_path, task_dir):
    log("Basic-Pitch AI 轉譜中...")
    from basic_pitch.inference import predict_and_save
    from basic_pitch import ICASSP_2022_MODEL_PATH

    midi_dir = task_dir / "midi_out"
    midi_dir.mkdir(exist_ok=True)

    # v0.2.6 的正確參數（不含 model_or_model_path）
    predict_and_save(
        [str(wav_path)],
        str(midi_dir),
        save_midi=True,
        sonify_midi=False,
        save_model_outputs=False,
        save_notes=False,
        minimum_frequency=27.5,
        maximum_frequency=4186.0
    )

    midi_files = list(midi_dir.glob("*.mid")) + list(midi_dir.glob("*.midi"))
    if not midi_files:
        raise RuntimeError("Basic-Pitch 未輸出 MIDI 檔案")

    log(f"轉譜完成：{midi_files[0].name}")
    return midi_files[0]

# ── STEP 3：MIDI → MusicXML ───────────────────────────────
def process_score(midi_path, task_dir, target_key, difficulty,
                  add_fingering, add_chord, add_pedal, add_tempo, simplify_left):
    log(f"music21 處理：調性={target_key}，難度={difficulty}")
    import music21
    from music21 import converter, stream, note, chord as m21chord, key as m21key, tempo, instrument

    score = converter.parse(str(midi_path))

    # 移調
    detected_key = score.analyze('key')
    source_semitones = KEY_SEMITONES.get(detected_key.tonic.name, 0)
    target_semitones = KEY_SEMITONES.get(target_key, 0)
    interval_diff = target_semitones - source_semitones
    if interval_diff != 0:
        from music21 import interval
        score = score.transpose(interval.Interval(interval_diff))
        log(f"移調：{detected_key.tonic.name} → {target_key}")

    diff_config = DIFFICULTY_MAP[difficulty]
    processed_score = stream.Score()
    processed_score.insert(0, m21key.Key(
        target_key.rstrip('m'),
        'minor' if target_key.endswith('m') else 'major'
    ))

    parts = list(score.parts)
    if not parts:
        raise RuntimeError("score 中沒有音軌")

    def extract_notes(part):
        result = []
        for el in part.flatten().notes:
            pitches = [el.pitch] if hasattr(el, 'pitch') else list(el.pitches)
            result.append((el.offset, el.quarterLength, pitches, getattr(el.volume, 'velocity', 64) or 64))
        return result

    if len(parts) == 1:
        all_notes = extract_notes(parts[0])
        treble_notes = [(o,d,[p for p in ps if p.midi>=60],v) for o,d,ps,v in all_notes if any(p.midi>=60 for p in ps)]
        bass_notes   = [(o,d,[p for p in ps if p.midi<60], v) for o,d,ps,v in all_notes if any(p.midi<60  for p in ps)]
    else:
        treble_notes = extract_notes(parts[0])
        bass_notes   = extract_notes(parts[1]) if len(parts) > 1 else []

    # 高音部
    treble_part = stream.Part()
    treble_part.insert(0, instrument.Piano())
    treble_part.insert(0, music21.clef.TrebleClef())

    for offset, duration, pitches, velocity in treble_notes:
        if not pitches:
            continue
        if diff_config["remove_octaves"]:
            pitches = [max(pitches, key=lambda p: p.midi)]
        if len(pitches) == 1 or diff_config["max_voices"] == 1:
            n = note.Note(pitches[0])
            n.quarterLength = duration
            treble_part.insert(offset, n)
        else:
            c = m21chord.Chord(pitches[:diff_config["max_voices"]])
            c.quarterLength = duration
            treble_part.insert(offset, c)

    # 低音部
    bass_part = stream.Part()
    bass_part.insert(0, instrument.Piano())
    bass_part.insert(0, music21.clef.BassClef())

    for offset, duration, pitches, velocity in bass_notes:
        if not pitches:
            continue
        if simplify_left:
            root = min(pitches, key=lambda p: p.midi)
            n = note.Note(root)
            n.quarterLength = max(duration, 1.0)
            bass_part.insert(offset, n)
        elif diff_config["simplify_chords"]:
            root = min(pitches, key=lambda p: p.midi)
            kept = [p for p in pitches if abs(p.midi - root.midi) in [0,7,12]][:2] or [root]
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

    if add_tempo:
        try:
            import pretty_midi
            pm = pretty_midi.PrettyMIDI(str(midi_path))
            tc = pm.get_tempo_changes()
            bpm = int(tc[1][0]) if len(tc[1]) > 0 else 120
        except:
            bpm = 120
        treble_part.insert(0, tempo.MetronomeMark(number=bpm))
        log(f"BPM：{bpm}")
    else:
        bpm = 120

    processed_score.append(treble_part)
    processed_score.append(bass_part)

    xml_path = task_dir / "score.xml"
    processed_score.write('musicxml', fp=str(xml_path))
    log(f"MusicXML 輸出：{xml_path}")

    total_measures = max(
        len(list(treble_part.getElementsByClass('Measure'))),
        len(list(bass_part.getElementsByClass('Measure'))),
        1
    )
    pages = max(1, total_measures // 16)
    return xml_path, pages, bpm

# ── STEP 4：MusicXML → PDF ────────────────────────────────
def export_pdf(xml_path, output_path):
    log(f"MuseScore 輸出 PDF：{output_path.name}")
    for cmd_name in ["mscore3", "musescore3", "musescore"]:
        try:
            result = subprocess.run(
                [cmd_name, "-o", str(output_path), str(xml_path)],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0 and output_path.exists():
                log(f"PDF 完成：{output_path.stat().st_size // 1024}KB")
                return
        except FileNotFoundError:
            continue
    raise RuntimeError("找不到 MuseScore，請確認已安裝 musescore3")

# ── MAIN ──────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task-id',       required=True)
    parser.add_argument('--url',           required=True)
    parser.add_argument('--key',           default='C')
    parser.add_argument('--difficulty',    default='intermediate',
                        choices=['beginner','intermediate','advanced'])
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
        wav_path, song_title = download_audio(args.url, task_dir)
        midi_path = transcribe_audio(wav_path, task_dir)

        # 釋放音源記憶體
        wav_path.unlink(missing_ok=True)

        xml_path, pages, bpm = process_score(
            midi_path, task_dir,
            target_key=args.key,
            difficulty=args.difficulty,
            add_fingering=bool(args.fingering),
            add_chord=bool(args.chord),
            add_pedal=bool(args.pedal),
            add_tempo=bool(args.tempo),
            simplify_left=bool(args.simplify_left)
        )

        # 釋放 MIDI 記憶體
        midi_path.unlink(missing_ok=True)

        safe_title = "".join(c for c in song_title if c.isalnum() or c in " _-")[:30]
        pdf_filename = f"{args.task_id}_{safe_title}_{args.key}_{args.difficulty}.pdf"
        pdf_path = OUTPUT_DIR / pdf_filename
        export_pdf(xml_path, pdf_path)

        generation_time = round(time.time() - start_time, 1)
        print(json.dumps({
            "success": True,
            "task_id": args.task_id,
            "pdf_path": str(pdf_path),
            "filename": pdf_filename,
            "pages": pages,
            "generation_time": generation_time,
            "song_title": song_title,
            "detected_bpm": bpm,
            "key": args.key,
            "difficulty": args.difficulty
        }, ensure_ascii=False))

    except Exception as e:
        log(f"錯誤：{e}")
        print(json.dumps({"success": False, "task_id": args.task_id, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
    finally:
        try:
            shutil.rmtree(task_dir)
        except:
            pass

if __name__ == "__main__":
    main()
