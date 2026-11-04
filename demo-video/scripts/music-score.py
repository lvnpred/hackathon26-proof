"""Generate one 30s score chunk with local MusicGen. Usage: music-score.py OUT PROMPT SEED"""
import sys
import torch
from transformers import MusicgenForConditionalGeneration, AutoProcessor

out, prompt, seed = sys.argv[1], sys.argv[2], int(sys.argv[3])
device = "mps" if torch.backends.mps.is_available() else "cpu"
model = MusicgenForConditionalGeneration.from_pretrained("facebook/musicgen-small").to(device)
processor = AutoProcessor.from_pretrained("facebook/musicgen-small")
model.generation_config.max_new_tokens = 50 * 30
model.generation_config.do_sample = True
model.generation_config.guidance_scale = 3.0
torch.manual_seed(seed)
inputs = processor(text=[prompt], padding=True, return_tensors="pt").to(device)
with torch.no_grad():
    audio = model.generate(**inputs).cpu()
sr = model.config.sampling_rate
import numpy as np
from scipy.io import wavfile
wav = (audio[0, 0].float().numpy() * 32767).astype(np.int16)
wavfile.write(out, sr, wav)
print("wrote", out, len(wav) / sr, "s", flush=True)
