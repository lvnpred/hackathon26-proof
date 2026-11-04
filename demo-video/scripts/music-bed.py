"""Generate the film's music bed with local MusicGen (facebook/musicgen-small). Deterministic seed."""
import sys
import torch
from transformers import MusicgenForConditionalGeneration, AutoProcessor

seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 10
out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/bed-probe.wav"
prompt = ("subtle ambient underscore, soft piano and strings pad, calm tension "
          "resolving to warm hope, cinematic, minimal, no drums, no vocals")

device = "mps" if torch.backends.mps.is_available() else "cpu"
print("device:", device, flush=True)
model = MusicgenForConditionalGeneration.from_pretrained("facebook/musicgen-small").to(device)
processor = AutoProcessor.from_pretrained("facebook/musicgen-small")
model.generation_config.max_new_tokens = int(50 * seconds)
model.generation_config.do_sample = True
model.generation_config.guidance_scale = 3.0
torch.manual_seed(7)
inputs = processor(text=[prompt], padding=True, return_tensors="pt").to(device)
with torch.no_grad():
    audio = model.generate(**inputs).cpu()
sr = model.config.sampling_rate
import numpy as np
from scipy.io import wavfile
wav = (audio[0, 0].float().numpy() * 32767).astype(np.int16)
wavfile.write(out, sr, wav)
print("wrote", out, len(wav) / sr, "s", flush=True)
