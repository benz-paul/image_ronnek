"""
Audio Generator Service - Generates TTS audio files using Amazon Polly.

Voice map (Amazon Polly standard voices):
  narrator   → Matthew (neutral US male)
  male_1     → Joey    (young US male)
  male_2     → Brian   (UK male)
  female_1   → Joanna  (neutral US female)
  female_2   → Ivy     (young US female)
  female_3   → Emma    (UK female)

Output folder structure:
  {run_folder}/audio/
    LS1/
      LS1_S1/
        narrator.mp3
        char_arjun.mp3
        char_priya.mp3
      LS1_S2/
        ...
    LS2/
      ...
    manifest.json
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError


# ---------------------------------------------------------------------------
# Voice palette — engine / voice / style kept for future extensibility
# (e.g. switching characters to Google WaveNet without changing JSON schema)
# ---------------------------------------------------------------------------
VOICE_MAP = {
    "narrator": {"engine": "polly", "voice": "Matthew", "style": "neutral"},
    "male_1":   {"engine": "polly", "voice": "Joey",    "style": "neutral"},
    "male_2":   {"engine": "polly", "voice": "Brian",   "style": "neutral"},
    "female_1": {"engine": "polly", "voice": "Joanna",  "style": "neutral"},
    "female_2": {"engine": "polly", "voice": "Ivy",     "style": "neutral"},
    "female_3": {"engine": "polly", "voice": "Emma",    "style": "neutral"},
}

# Default Polly voice if character's voice_id is missing
DEFAULT_NARRATOR_VOICE = "Matthew"
DEFAULT_MALE_VOICE = "Joey"
DEFAULT_FEMALE_VOICE = "Joanna"


class AudioGeneratorService:
    """
    Generates MP3 audio files from scene narrator text and character dialogues
    using Amazon Polly standard TTS.
    """

    def __init__(self, run_folder: str):
        """
        Initialize the service.

        Args:
            run_folder: Path to the pipeline run folder.
                        Audio files are saved under run_folder/audio/
        """
        self.run_folder = Path(run_folder)
        self.audio_dir = self.run_folder / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        # Initialize Polly client from environment variables
        aws_key = os.getenv("AWS_ACCESS_KEY_ID")
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

    def _synthesize(self, text: str, voice_id: str) -> bytes:
        """
        Call Amazon Polly synthesize_speech and return raw MP3 bytes.

        Args:
            text:     Clean prose text to synthesize.
            voice_id: Amazon Polly VoiceId string (e.g. "Matthew", "Joanna").

        Returns:
            Raw MP3 bytes.
        """
        if not text or not text.strip():
            return b""

        try:
            response = self.polly.synthesize_speech(
                Text=text.strip(),
                OutputFormat="mp3",
                VoiceId=voice_id,
            )
            return response["AudioStream"].read()
        except (BotoCoreError, ClientError) as e:
            print(f"[AUDIO ERROR] Polly synthesis failed for voice {voice_id}: {e}")
            return b""

    def generate_narrator_audio(
        self,
        ls_index: int,
        scene_id: str,
        narrator_text: str,
        voice_id: str = DEFAULT_NARRATOR_VOICE,
    ) -> str:
        """
        Generate narrator MP3 for a single scene.

        Args:
            ls_index:      0-based learning step index.
            scene_id:      Scene ID string (e.g. "LS1_S1").
            narrator_text: Clean prose narration text.
            voice_id:      Polly voice for narrator (default: Matthew).

        Returns:
            Path to saved narrator.mp3, or "" if synthesis failed.
        """
        ls_key = f"LS{ls_index + 1}"
        scene_dir = self.audio_dir / ls_key / scene_id
        scene_dir.mkdir(parents=True, exist_ok=True)

        filepath = scene_dir / "narrator.mp3"
        audio_bytes = self._synthesize(narrator_text, voice_id)

        if audio_bytes:
            filepath.write_bytes(audio_bytes)
            print(f"[AUDIO] narrator.mp3 → audio/{ls_key}/{scene_id}/narrator.mp3")
            return str(filepath)

        print(f"[AUDIO WARNING] No narrator audio for {scene_id}")
        return ""

    def generate_character_audio(
        self,
        ls_index: int,
        scene_id: str,
        char_id: str,
        audio_text: str,
        voice_id: str,
    ) -> str:
        """
        Generate character dialogue MP3 for a single scene.

        Args:
            ls_index:   0-based learning step index.
            scene_id:   Scene ID string (e.g. "LS1_S1").
            char_id:    Character identifier (used as filename).
            audio_text: Clean dialogue text for TTS.
            voice_id:   Polly VoiceId for this character.

        Returns:
            Path to saved char_{char_id}.mp3, or "" if synthesis failed.
        """
        ls_key = f"LS{ls_index + 1}"
        scene_dir = self.audio_dir / ls_key / scene_id
        scene_dir.mkdir(parents=True, exist_ok=True)

        safe_id = char_id.lower().replace(" ", "_")
        filepath = scene_dir / f"char_{safe_id}.mp3"

        audio_bytes = self._synthesize(audio_text, voice_id)

        if audio_bytes:
            filepath.write_bytes(audio_bytes)
            print(
                f"[AUDIO] char_{safe_id}.mp3 → audio/{ls_key}/{scene_id}/char_{safe_id}.mp3"
            )
            return str(filepath)

        print(f"[AUDIO WARNING] No audio for character {char_id} in {scene_id}")
        return ""

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
            scene:            Scene dict (must have narrator_audio_text and
                              character_dialogues fields).
            ls_id:            Learning step ID string (e.g. "LS1").
            ls_index:         0-based learning step index.
            narrator_voice_id: Polly voice for narrator.

        Returns:
            Dict mapping audio type → file path:
            {
                "narrator": "path/to/narrator.mp3",
                "characters": {
                    "arjun": "path/to/char_arjun.mp3",
                    ...
                }
            }
        """
        scene_id = scene.get("scene_id", "unknown")
        # Normalise scene_id: ensure it includes LS prefix (e.g. LS1_S1)
        if not scene_id.startswith(ls_id):
            scene_id = f"{ls_id}_{scene_id}"

        result: Dict[str, Any] = {"narrator": "", "characters": {}}

        # Narrator audio
        narrator_text = scene.get("narrator_audio_text", "")
        if narrator_text:
            narrator_path = self.generate_narrator_audio(
                ls_index=ls_index,
                scene_id=scene_id,
                narrator_text=narrator_text,
                voice_id=narrator_voice_id,
            )
            result["narrator"] = narrator_path

        # Character dialogue audio
        char_dialogues = scene.get("character_dialogues", [])
        for cd in char_dialogues:
            if not isinstance(cd, dict):
                continue
            char_id = cd.get("character_id", "")
            voice_id = cd.get("voice_id", DEFAULT_MALE_VOICE)
            audio_text = cd.get("audio_text", cd.get("dialogue", ""))

            if char_id and audio_text:
                char_path = self.generate_character_audio(
                    ls_index=ls_index,
                    scene_id=scene_id,
                    char_id=char_id,
                    audio_text=audio_text,
                    voice_id=voice_id,
                )
                if char_path:
                    result["characters"][char_id] = char_path

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
            scenes_by_ls:       Dict mapping ls_id → list of scene dicts.
                                e.g. {"LS1": [scene1, scene2], "LS2": [...]}
            narrator_voice_id:  Polly voice for the narrator.
            learning_steps_list: Optional list to infer ls_index from ls_id.

        Returns:
            Full audio manifest:
            {
                "LS1": {
                    "LS1_S1": {"narrator": "path/...", "characters": {...}},
                    ...
                },
                ...
            }
        """
        # Build ls_id → ls_index mapping
        ls_index_map: Dict[str, int] = {}
        if learning_steps_list:
            for i, ls in enumerate(learning_steps_list):
                ls_id = ls.get("learning_step_id", f"LS{i + 1}")
                ls_index_map[ls_id] = i
        else:
            # Fallback: infer index from sorted keys
            for i, ls_id in enumerate(sorted(scenes_by_ls.keys())):
                ls_index_map[ls_id] = i

        manifest: Dict[str, Any] = {}
        total_scenes = sum(len(v) for v in scenes_by_ls.values())
        processed = 0

        for ls_id, scenes in scenes_by_ls.items():
            ls_index = ls_index_map.get(ls_id, 0)
            manifest[ls_id] = {}

            for scene in scenes:
                processed += 1
                scene_id = scene.get("scene_id", f"S{processed}")
                if not scene_id.startswith(ls_id):
                    scene_id = f"{ls_id}_{scene_id}"

                print(
                    f"[AUDIO] Processing {scene_id} ({processed}/{total_scenes})"
                )

                audio_result = self.generate_audio_for_scene(
                    scene=scene,
                    ls_id=ls_id,
                    ls_index=ls_index,
                    narrator_voice_id=narrator_voice_id,
                )
                manifest[ls_id][scene_id] = audio_result

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
