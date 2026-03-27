"""
Audio Generator Service - Generates TTS audio files using Amazon Polly.

Character voice map (resolved by character name, overrides scene JSON voice_id):
  leo / joey   → Kevin   (neural, young US male teen)
  maya         → Ivy     (standard, young US female)
  mr_chen      → Matthew (neural, warm adult US male teacher)
  mr_aris      → Matthew (neural, warm adult US male mentor)
  narrator     → Gregory (neural, deep adult US male — distinct from teachers)

Emotion → SSML:
  Matthew (neural) : <amazon:emotion name="excited/disappointed">
  Kid voices       : <prosody pitch/rate> adjustments for energy
  All kids         : baseline +5% pitch boost so they never sound adult

Output folder structure:
  {run_folder}/audio/
    LS1/
      LS1_S1/
        narrator.mp3
        dialogue_01.mp3
        dialogue_02.mp3
      LS1_S2/
        ...
    manifest.json
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

try:
    from mutagen.mp3 import MP3 as MutagenMP3
    _HAS_MUTAGEN = True
except ImportError:
    _HAS_MUTAGEN = False

try:
    from pydub import AudioSegment
    import shutil as _shutil
    _HAS_PYDUB = True
    # Check system PATH first, then fall back to project-local bin/ffmpeg.exe
    _LOCAL_FFMPEG = Path(__file__).parent.parent.parent / "bin" / "ffmpeg.exe"
    _system_ffmpeg = _shutil.which("ffmpeg") or _shutil.which("avconv")
    if _system_ffmpeg:
        _HAS_FFMPEG = True
    elif _LOCAL_FFMPEG.exists():
        AudioSegment.converter = str(_LOCAL_FFMPEG)
        _HAS_FFMPEG = True
    else:
        _HAS_FFMPEG = False
except ImportError:
    _HAS_PYDUB = False
    _HAS_FFMPEG = False


def _get_mp3_duration_ms(filepath: str) -> int:
    """Return duration of an MP3 file in milliseconds. Returns 0 if mutagen unavailable."""
    if not _HAS_MUTAGEN:
        return 0
    try:
        return int(MutagenMP3(filepath).info.length * 1000)
    except Exception:
        return 0


def merge_scene_audio(
    scene_audio_dir: str,
    output_path: str,
    narrator_silence_ms: int = 600,
    dialogue_silence_ms: int = 400,
) -> str:
    """
    Merge narrator.mp3 + dialogue_NN.mp3 files into a single combined.mp3 per scene.
    Structure: narrator → 600ms silence → dialogue_01 → 400ms silence → dialogue_02 → ...

    Args:
        scene_audio_dir: Path to LS1/LS1_S1/ folder
        output_path: Where to write combined.mp3
        narrator_silence_ms: Gap after narrator before first dialogue
        dialogue_silence_ms: Gap between dialogue lines

    Returns:
        Path to merged file, or empty string if pydub unavailable or no audio found.
    """
    if not _HAS_PYDUB:
        print("[AUDIO MERGE] pydub not available — skipping merge. Run: pip install pydub")
        return ""
    if not _HAS_FFMPEG:
        print("[AUDIO MERGE] ffmpeg not found — skipping merge. Install ffmpeg and add to PATH.")
        return ""

    scene_dir = Path(scene_audio_dir)
    narrator_path = scene_dir / "narrator.mp3"

    if not narrator_path.exists():
        print(f"[AUDIO MERGE] narrator.mp3 not found in {scene_dir}, skipping")
        return ""

    try:
        combined = AudioSegment.from_mp3(str(narrator_path))

        dialogue_files = sorted(scene_dir.glob("dialogue_*.mp3"))
        if dialogue_files:
            combined += AudioSegment.silent(duration=narrator_silence_ms)
            for i, dlg_path in enumerate(dialogue_files):
                combined += AudioSegment.from_mp3(str(dlg_path))
                if i < len(dialogue_files) - 1:
                    combined += AudioSegment.silent(duration=dialogue_silence_ms)

        combined.export(output_path, format="mp3")
        duration_ms = len(combined)
        print(f"[AUDIO MERGE] {Path(output_path).name} — {1 + len(dialogue_files)} segments, {duration_ms}ms")
        return output_path

    except Exception as e:
        print(f"[AUDIO MERGE ERROR] {e}")
        return ""


# ---------------------------------------------------------------------------
# Character → Polly voice  (name-based, overrides scene JSON voice_id)
# ---------------------------------------------------------------------------
CHARACTER_VOICE_MAP: Dict[str, Dict[str, str]] = {
    # Our story characters
    "leo":     {"voice": "Kevin",   "engine": "neural"},     # teen boy
    "maya":    {"voice": "Ivy",     "engine": "standard"},   # teen girl
    "mr_chen": {"voice": "Matthew", "engine": "neural"},     # adult teacher
    "mrchen":  {"voice": "Matthew", "engine": "neural"},     # alias (scene naming)
    # Teammate's original characters (kept for compatibility)
    "mr_aris": {"voice": "Matthew", "engine": "neural"},     # adult mentor
    "mraris":  {"voice": "Matthew", "engine": "neural"},     # alias
    "joey":    {"voice": "Kevin",   "engine": "neural"},     # forward-compat alias
    # Narrator — distinct adult male, different from teachers
    "narrator":{"voice": "Gregory", "engine": "neural"},     # deep narrator voice
    # Custom characters (Doraemon/Nobita demo)
    "doraemon": {"voice": "Matthew", "engine": "neural"},    # robot cat — warm adult
    "nobita":   {"voice": "Kevin",   "engine": "neural"},    # schoolboy
    "shizuka":  {"voice": "Ivy",     "engine": "standard"},  # schoolgirl
}

# Fallbacks when character not in map
DEFAULT_NARRATOR_VOICE  = "Gregory"
DEFAULT_NARRATOR_ENGINE = "neural"
DEFAULT_MALE_VOICE      = "Kevin"
DEFAULT_FEMALE_VOICE    = "Ivy"

# Kid voice IDs — always get a baseline pitch boost so they sound young
KID_VOICES = {"Kevin", "Ivy", "Justin"}

# ---------------------------------------------------------------------------
# Emotion → SSML templates
#
#   "matthew" — Matthew neural  → <amazon:emotion> tag (richest expression)
#   "kids"    — Kevin / Ivy     → stronger prosody (energetic, lively)
#   "default" — any other       → moderate prosody
# ---------------------------------------------------------------------------
EMOTION_SSML: Dict[str, Dict[str, str]] = {
    "happy": {
        "matthew": '<amazon:emotion name="excited" intensity="high">{text}</amazon:emotion>',
        "kids":    '<prosody pitch="+18%" rate="fast" volume="loud">{text}</prosody>',
        "default": '<prosody pitch="+10%" rate="fast">{text}</prosody>',
    },
    "sad": {
        "matthew": '<amazon:emotion name="disappointed" intensity="high">{text}</amazon:emotion>',
        "kids":    '<prosody pitch="-14%" rate="80%" volume="soft">{text}</prosody>',
        "default": '<prosody pitch="-10%" rate="slow">{text}</prosody>',
    },
    "curious": {
        "matthew": '<prosody pitch="+8%" rate="85%">{text}</prosody>',
        "kids":    '<prosody pitch="+10%" rate="85%" volume="medium">{text}</prosody>',
        "default": '<prosody pitch="+6%" rate="90%">{text}</prosody>',
    },
    "excited": {
        "matthew": '<amazon:emotion name="excited" intensity="medium">{text}</amazon:emotion>',
        "kids":    '<prosody pitch="+15%" rate="fast" volume="loud">{text}</prosody>',
        "default": '<prosody pitch="+8%" rate="fast">{text}</prosody>',
    },
    "frustrated": {
        "matthew": '<amazon:emotion name="disappointed" intensity="medium">{text}</amazon:emotion>',
        "kids":    '<prosody pitch="-8%" rate="95%" volume="medium">{text}</prosody>',
        "default": '<prosody pitch="-6%" rate="95%">{text}</prosody>',
    },
}


def _build_ssml(text: str, voice_id: str, engine: str, emotion: Optional[str]) -> str:
    """
    Wrap plain text in an SSML <speak> block.

    Template selection:
      - "matthew" key  → Matthew neural (amazon:emotion supported)
      - "kids"    key  → Kevin / Ivy (strong prosody, teen energy)
      - "default" key  → everyone else

    Baseline: kid voices always get +5% pitch even with no emotion so they
    never sound adult.
    """
    clean = text.strip()
    inner = clean

    if emotion and emotion.lower() in EMOTION_SSML:
        if voice_id == "Matthew":
            tmpl_key = "matthew"
        elif voice_id in KID_VOICES:
            tmpl_key = "kids"
        else:
            tmpl_key = "default"
        inner = EMOTION_SSML[emotion.lower()][tmpl_key].format(text=clean)
    elif voice_id in KID_VOICES:
        # Baseline: teens always sound younger than adults
        inner = f'<prosody pitch="+5%">{clean}</prosody>'

    if inner == clean:
        return clean  # no SSML needed — return plain text

    return f"<speak>{inner}</speak>"


class AudioGeneratorService:
    """
    Generates MP3 audio files from scene narrator text and character dialogues
    using Amazon Polly.  Character voices are resolved by name (not by the
    voice_id field in the scene JSON) so that casting is controlled centrally.
    """

    def __init__(self, run_folder: str):
        self.run_folder = Path(run_folder)
        self.audio_dir = self.run_folder / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        aws_key    = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret = os.getenv("AWS_SECRET_ACCESS_KEY")
        aws_region = os.getenv("AWS_REGION", "us-east-1")

        if not aws_key or not aws_secret:
            raise ValueError(
                "AWS credentials not found. Set AWS_ACCESS_KEY_ID and "
                "AWS_SECRET_ACCESS_KEY in your .env file."
            )

        self.polly = boto3.client(
            "polly",
            aws_access_key_id=aws_key,
            aws_secret_access_key=aws_secret,
            region_name=aws_region,
        )
        print(f"[AUDIO] Polly client initialized (region: {aws_region})")

    # ------------------------------------------------------------------
    # Internal synthesis
    # ------------------------------------------------------------------

    def _synthesize(
        self,
        text: str,
        voice_id: str,
        engine: str = "standard",
        emotion: Optional[str] = None,
    ) -> bytes:
        """
        Call Amazon Polly and return raw MP3 bytes.

        Args:
            text:     Plain prose to synthesize.
            voice_id: Amazon Polly VoiceId (e.g. "Matthew", "Kevin").
            engine:   "standard" or "neural".
            emotion:  Optional emotion hint ("happy", "sad", "curious", etc.).
        """
        if not text or not text.strip():
            return b""

        ssml_or_text = _build_ssml(text, voice_id, engine, emotion)
        is_ssml = ssml_or_text.startswith("<speak>")

        try:
            kwargs: Dict[str, Any] = {
                "Text":         ssml_or_text,
                "TextType":     "ssml" if is_ssml else "text",
                "OutputFormat": "mp3",
                "VoiceId":      voice_id,
            }
            if engine == "neural":
                kwargs["Engine"] = "neural"

            response = self.polly.synthesize_speech(**kwargs)
            return response["AudioStream"].read()
        except (BotoCoreError, ClientError) as e:
            print(f"[AUDIO ERROR] Polly failed — voice={voice_id} engine={engine}: {e}")
            return b""

    # ------------------------------------------------------------------
    # Public generation methods
    # ------------------------------------------------------------------

    def generate_narrator_audio(
        self,
        ls_index: int,
        scene_id: str,
        narrator_text: str,
        voice_id: str = DEFAULT_NARRATOR_VOICE,
        engine: str = DEFAULT_NARRATOR_ENGINE,
    ) -> Dict[str, Any]:
        """
        Generate narrator MP3 for a single scene.

        Returns:
            {"path": "...", "duration_ms": N} or {"path": "", "duration_ms": 0}
        """
        ls_key    = f"LS{ls_index + 1}"
        scene_dir = self.audio_dir / ls_key / scene_id
        scene_dir.mkdir(parents=True, exist_ok=True)

        filepath    = scene_dir / "narrator.mp3"
        audio_bytes = self._synthesize(narrator_text, voice_id, engine)

        if audio_bytes:
            filepath.write_bytes(audio_bytes)
            dur = _get_mp3_duration_ms(str(filepath))
            print(f"[AUDIO] narrator.mp3 → audio/{ls_key}/{scene_id}/narrator.mp3 ({dur}ms)")
            return {"path": str(filepath), "duration_ms": dur}

        print(f"[AUDIO WARNING] No narrator audio for {scene_id}")
        return {"path": "", "duration_ms": 0}

    def generate_character_audio(
        self,
        ls_index: int,
        scene_id: str,
        char_id: str,
        audio_text: str,
        voice_id: str,
        engine: str = "standard",
        emotion: Optional[str] = None,
        dialogue_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate character dialogue MP3 for a single scene.
        Files are named dialogue_NN.mp3 (sequential) for ordered playback.

        Returns:
            {"path": "...", "duration_ms": N, "speaker": "..."} or empty dict.
        """
        ls_key    = f"LS{ls_index + 1}"
        scene_dir = self.audio_dir / ls_key / scene_id
        scene_dir.mkdir(parents=True, exist_ok=True)

        if dialogue_index is not None:
            filename = f"dialogue_{dialogue_index:02d}.mp3"
        else:
            safe_id  = char_id.lower().replace(" ", "_")
            filename = f"char_{safe_id}.mp3"

        filepath    = scene_dir / filename
        audio_bytes = self._synthesize(audio_text, voice_id, engine, emotion)

        if audio_bytes:
            filepath.write_bytes(audio_bytes)
            dur = _get_mp3_duration_ms(str(filepath))
            print(f"[AUDIO] {filename} → audio/{ls_key}/{scene_id}/{filename} ({dur}ms)")
            return {"path": str(filepath), "duration_ms": dur, "speaker": char_id}

        print(f"[AUDIO WARNING] No audio for {char_id} in {scene_id}")
        return {}

    def generate_audio_for_scene(
        self,
        scene: Dict[str, Any],
        ls_id: str,
        ls_index: int,
        narrator_voice_id: str = DEFAULT_NARRATOR_VOICE,
    ) -> Dict[str, Any]:
        """
        Generate all audio (narrator + all characters) for a single scene.

        Args:
            scene:             Scene dict with narrator_audio_text and character_dialogues.
            ls_id:             Learning step ID (e.g. "LS1").
            ls_index:          0-based learning step index.
            narrator_voice_id: Polly voice for narrator.

        Returns:
            {
                "narrator": "path/to/narrator.mp3",
                "characters": {
                    "dialogue_01": "path/to/dialogue_01.mp3",
                    ...
                }
            }
        """
        scene_id = scene.get("scene_id", "unknown")
        if not scene_id.startswith(ls_id):
            scene_id = f"{ls_id}_{scene_id}"

        result: Dict[str, Any] = {
            "narrator": {"path": "", "duration_ms": 0},
            "characters": {},
            "dialogues": [],  # ordered list with timing info
        }

        # Narrator
        narrator_text = scene.get("narrator_audio_text", "")
        if narrator_text:
            narrator_result = self.generate_narrator_audio(
                ls_index=ls_index,
                scene_id=scene_id,
                narrator_text=narrator_text,
                voice_id=narrator_voice_id,
                engine=DEFAULT_NARRATOR_ENGINE,
            )
            result["narrator"] = narrator_result

        # Character dialogues — sequential naming: dialogue_01, dialogue_02 …
        char_dialogues  = scene.get("character_dialogues", [])
        dialogue_counter = 1
        running_ms = result["narrator"]["duration_ms"]  # dialogues start after narrator

        for cd in char_dialogues:
            if not isinstance(cd, dict):
                continue

            char_id    = cd.get("character_id", "").lower().strip()
            audio_text = cd.get("audio_text", cd.get("dialogue", ""))
            emotion    = cd.get("emotion")  # None if not in scene JSON

            # Resolve voice by character name — ignore whatever voice_id the scene says
            char_cfg = CHARACTER_VOICE_MAP.get(char_id)
            if char_cfg:
                voice_id = char_cfg["voice"]
                engine   = char_cfg["engine"]
            else:
                # Unknown character: fall back to scene JSON voice_id
                voice_id = cd.get("voice_id", DEFAULT_MALE_VOICE)
                engine   = "standard"
                print(f"[AUDIO] Unknown character '{char_id}', using fallback voice {voice_id}")

            if char_id and audio_text:
                char_result = self.generate_character_audio(
                    ls_index=ls_index,
                    scene_id=scene_id,
                    char_id=char_id,
                    audio_text=audio_text,
                    voice_id=voice_id,
                    engine=engine,
                    emotion=emotion,
                    dialogue_index=dialogue_counter,
                )
                if char_result:
                    key = f"dialogue_{dialogue_counter:02d}"
                    result["characters"][key] = char_result.get("path", "")
                    result["dialogues"].append({
                        "id": key,
                        "speaker": char_id,
                        "duration_ms": char_result.get("duration_ms", 0),
                        "start_ms": running_ms,
                    })
                    running_ms += char_result.get("duration_ms", 0)
                    dialogue_counter += 1

        result["total_duration_ms"] = running_ms
        return result

    def generate_audio_for_all_scenes(
        self,
        scenes_by_ls: Dict[str, List[Dict[str, Any]]],
        narrator_voice_id: str = DEFAULT_NARRATOR_VOICE,
        learning_steps_list: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Generate audio for all scenes across all learning steps.

        Args:
            scenes_by_ls:        Dict mapping ls_id → list of scene dicts.
                                 e.g. {"LS1": [scene1, scene2], "LS2": [...]}
            narrator_voice_id:   Polly voice for the narrator.
            learning_steps_list: Optional list to infer ls_index from ls_id.

        Returns:
            Full audio manifest dict.
        """
        # Build ls_id → ls_index mapping
        ls_index_map: Dict[str, int] = {}
        if learning_steps_list:
            for i, ls in enumerate(learning_steps_list):
                ls_id = ls.get("learning_step_id", f"LS{i + 1}")
                ls_index_map[ls_id] = i
        else:
            for i, ls_id in enumerate(sorted(scenes_by_ls.keys())):
                ls_index_map[ls_id] = i

        manifest: Dict[str, Any] = {}
        total_scenes = sum(len(v) for v in scenes_by_ls.values())
        processed    = 0

        for ls_id, scenes in scenes_by_ls.items():
            ls_index        = ls_index_map.get(ls_id, 0)
            manifest[ls_id] = {}

            for scene in scenes:
                processed += 1
                scene_id   = scene.get("scene_id", f"S{processed}")
                if not scene_id.startswith(ls_id):
                    scene_id = f"{ls_id}_{scene_id}"

                print(f"[AUDIO] Processing {scene_id} ({processed}/{total_scenes})")

                audio_result = self.generate_audio_for_scene(
                    scene=scene,
                    ls_id=ls_id,
                    ls_index=ls_index,
                    narrator_voice_id=narrator_voice_id,
                )
                manifest[ls_id][scene_id] = audio_result

        # Merge each scene's audio into a single combined.mp3
        print(f"[AUDIO] Merging scene audio files...")
        for ls_id, scenes_map in manifest.items():
            for scene_id, audio_result in scenes_map.items():
                scene_dir = self.audio_dir / ls_id / scene_id
                combined_path = str(self.audio_dir / ls_id / f"{scene_id}.mp3")
                merged = merge_scene_audio(
                    scene_audio_dir=str(scene_dir),
                    output_path=combined_path,
                )
                if merged:
                    manifest[ls_id][scene_id]["combined_path"] = combined_path
                    manifest[ls_id][scene_id]["combined_duration_ms"] = (
                        _get_mp3_duration_ms(combined_path)
                    )

        # Save manifest
        manifest_path = self.audio_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        print(f"[AUDIO] Manifest saved → audio/manifest.json")
        print(
            f"[AUDIO] Done. Generated audio for {processed} scenes across "
            f"{len(scenes_by_ls)} learning steps."
        )
        return manifest
