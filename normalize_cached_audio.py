import subprocess
import glob
import re
import os

if not os.path.exists('normalized'):
    os.mkdir('normalized')
    os.mkdir(os.path.join('normalized', 'cache'))

audio_files = glob.glob('cache/*.m4a')
for audio_file in audio_files:
    probe = subprocess.run(['ffmpeg', '-hide_banner', '-i', audio_file, '-filter:a', 'volumedetect', '-vn', '-sn', '-dn', '-f', 'null', '/dev/null'], stderr=subprocess.PIPE, text=True)
    matches = re.search(r'max_volume\: (.*) dB', probe.stderr)
    if not matches:
        print(f'Failed to get volume info for {audio_file}')
        exit()
    max_db = float(matches[1])

    print(f'Track "{audio_file}" has max volume of {max_db} dB - normalization value will be {abs(max_db)} dB')

    subprocess.call(['ffmpeg', '-y', '-i', audio_file, '-filter:a', f'volume={abs(max_db)}dB', '-b:a', '256k', f'normalized/{audio_file}'])
    