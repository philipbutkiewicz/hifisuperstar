import glob
import os
import re
import subprocess

os.makedirs(os.path.join("normalized", "cache"), exist_ok=True)

audio_files = glob.glob("cache/*.m4a")
for audio_file in audio_files:
    if not os.path.exists(os.path.join("normalized", audio_file)):
        probe = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-i",
                audio_file,
                "-filter:a",
                "volumedetect",
                "-vn",
                "-sn",
                "-dn",
                "-f",
                "null",
                "/dev/null",
            ],
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        matches = re.search(r"max_volume\: (.*) dB", probe.stderr)
        if not matches:
            print(f"Failed to get volume info for {audio_file}")
            continue
        max_db = float(matches[1])

        print(
            f'Track "{audio_file}" has max volume of {max_db} dB - normalization value will be {abs(max_db)} dB'
        )

        # Write to a temporary file first: the bot prefers normalized files and must never see a partial one
        output_path = os.path.join("normalized", audio_file)
        temporary_path = f"{output_path}.tmp.m4a"
        result = subprocess.call(
            [
                "ffmpeg",
                "-y",
                "-i",
                audio_file,
                "-filter:a",
                f"volume={abs(max_db)}dB",
                "-b:a",
                "256k",
                temporary_path,
            ]
        )
        if result == 0:
            os.replace(temporary_path, output_path)
        else:
            print(f"Failed to normalize {audio_file}")
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
    else:
        print(f'Cached audio file "{audio_file}" is already normalized.')
