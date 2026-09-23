import numpy as np
from scipy.io import wavfile
import subprocess
import os

sample_rate = 44100
duration = 32.0  # seconds
num_samples = int(sample_rate * duration)

t = np.linspace(0, duration, num_samples, endpoint=False)

# BPM & Grid
bpm = 85
beat_dur = 60.0 / bpm
bar_dur = beat_dur * 4

# Chord Progression (Cmaj7 -> Am7 -> Dm7 -> G7)
# Frequencies in Hz
chords_freqs = [
    [261.63, 329.63, 392.00, 493.88],  # Cmaj7 (C4, E4, G4, B4)
    [220.00, 261.63, 329.63, 392.00],  # Am7   (A3, C4, E4, G4)
    [146.83, 174.61, 220.00, 261.63],  # Dm7   (D3, F3, A3, C4)
    [196.00, 246.94, 293.66, 349.23],  # G7    (G3, B3, D4, F4)
]

bass_freqs = [130.81, 110.00, 73.42, 98.00] # C3, A2, D2, G2

# Initialize audio channels
synth_track = np.zeros(num_samples)
bass_track = np.zeros(num_samples)
drum_track = np.zeros(num_samples)

# Generate Synth Chords (Rhodes-like EP piano with soft harmonics)
for i in range(num_samples):
    time = t[i]
    bar_idx = int(time / bar_dur) % len(chords_freqs)
    chord = chords_freqs[bar_idx]
    
    # Slight tape wow & flutter pitch wobble
    wobble = 1.0 + 0.003 * np.sin(2 * np.pi * 1.5 * time)
    
    # Envelope within each bar (soft attack, decay)
    bar_time = time % bar_dur
    env = np.exp(-1.2 * (bar_time % beat_dur)) * 0.4 + 0.6 * np.exp(-0.4 * bar_time)
    
    chord_wave = 0.0
    for freq in chord:
        f = freq * wobble
        # Fundamental + warm harmonics
        wave = (np.sin(2 * np.pi * f * time) + 
                0.3 * np.sin(2 * np.pi * f * 2 * time) + 
                0.1 * np.sin(2 * np.pi * f * 3 * time))
        chord_wave += wave
    
    synth_track[i] = chord_wave * env

# Generate Upbeat Bassline
for i in range(num_samples):
    time = t[i]
    bar_idx = int(time / bar_dur) % len(bass_freqs)
    b_freq = bass_freqs[bar_idx]
    beat_idx = int(time / beat_dur) % 4
    
    # Pluck envelope on beats 1 and 3, plus syncopated 8th note
    sub_beat = (time % beat_dur) / beat_dur
    beat_env = np.exp(-6.0 * sub_beat)
    
    if beat_idx in [0, 2] or (beat_idx == 1 and sub_beat > 0.5):
        bass_wave = np.sin(2 * np.pi * b_freq * time) + 0.4 * np.sin(2 * np.pi * b_freq * 2 * time)
        bass_track[i] = bass_wave * beat_env

# Generate Upbeat Lo-Fi Drum Beat (Kick, Snare, Hi-Hat)
kick_times = [0.0, 1.5, 2.0, 3.25] # beats in a bar
snare_times = [1.0, 3.0]          # backbeat on 2 and 4

for bar in range(int(duration / bar_dur) + 1):
    bar_start = bar * bar_dur
    
    # Kick Drums
    for k_beat in kick_times:
        k_time = bar_start + k_beat * beat_dur
        k_sample = int(k_time * sample_rate)
        k_dur = int(0.18 * sample_rate)
        if k_sample < num_samples:
            end = min(k_sample + k_dur, num_samples)
            dur_len = end - k_sample
            t_k = np.linspace(0, 0.18, dur_len)
            freq_env = 120 * np.exp(-30 * t_k) + 45
            amp_env = np.exp(-12 * t_k)
            kick = np.sin(2 * np.pi * freq_env * t_k) * amp_env
            drum_track[k_sample:end] += kick * 0.8
            
    # Snare Drums
    for s_beat in snare_times:
        s_time = bar_start + s_beat * beat_dur
        s_sample = int(s_time * sample_rate)
        s_dur = int(0.15 * sample_rate)
        if s_sample < num_samples:
            end = min(s_sample + s_dur, num_samples)
            dur_len = end - s_sample
            t_s = np.linspace(0, 0.15, dur_len)
            noise = np.random.uniform(-1, 1, dur_len) * np.exp(-25 * t_s)
            body = np.sin(2 * np.pi * 180 * t_s) * np.exp(-30 * t_s)
            snare = (noise * 0.7 + body * 0.3)
            drum_track[s_sample:end] += snare * 0.5
            
    # Hi-Hats (16th note rhythm)
    for h in range(16):
        h_time = bar_start + (h * 0.25) * beat_dur
        h_sample = int(h_time * sample_rate)
        h_dur = int(0.04 * sample_rate)
        if h_sample < num_samples:
            end = min(h_sample + h_dur, num_samples)
            dur_len = end - h_sample
            t_h = np.linspace(0, 0.04, dur_len)
            accent = 0.6 if h % 2 == 0 else 0.35
            hat = np.random.uniform(-1, 1, dur_len) * np.exp(-80 * t_h) * accent
            drum_track[h_sample:end] += hat * 0.3

# Vinyl Crackle Texture
vinyl_crackle = np.random.uniform(-1, 1, num_samples) * 0.015
pops = np.random.choice([0, 1], size=num_samples, p=[0.9995, 0.0005]) * np.random.uniform(-0.1, 0.1, num_samples)
vinyl = vinyl_crackle + pops

# Mix all stems
master = (synth_track * 0.25) + (bass_track * 0.35) + (drum_track * 0.45) + (vinyl * 0.1)

# Normalize audio peak
master = master / np.max(np.abs(master)) * 0.85
master_i16 = (master * 32767).astype(np.int16)

wav_out = "/config/.gemini/antigravity/scratch/recipe-assistant/lofi_beat.wav"
wavfile.write(wav_out, sample_rate, master_i16)
print("Generated upbeat lo-fi track:", wav_out)

# Use ffmpeg binary to combine audio with demo video
import imageio_ffmpeg
ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

artifact_dir = "/config/.gemini/antigravity/brain/e207a180-80b9-4291-ae85-c9e9700c55ec"
input_video = os.path.join(artifact_dir, "demo_recording.webm")
output_webm = os.path.join(artifact_dir, "demo_recording_lofi.webm")
output_mp4 = os.path.join(artifact_dir, "demo_recording_lofi.mp4")

# Mix into WebM (Vorbis/Opus audio + VP8/VP9 video)
cmd_webm = [
    ffmpeg_exe, "-y",
    "-i", input_video,
    "-i", wav_out,
    "-c:v", "copy",
    "-c:a", "libvorbis",
    "-shortest",
    output_webm
]
subprocess.run(cmd_webm, check=True)
print("Saved WebM with lo-fi music:", output_webm)

# Mix into MP4 (AAC audio + H264 video)
cmd_mp4 = [
    ffmpeg_exe, "-y",
    "-i", input_video,
    "-i", wav_out,
    "-c:v", "libx264",
    "-preset", "fast",
    "-c:a", "aac",
    "-b:a", "192k",
    "-shortest",
    output_mp4
]
subprocess.run(cmd_mp4, check=True)
print("Saved MP4 with lo-fi music:", output_mp4)
