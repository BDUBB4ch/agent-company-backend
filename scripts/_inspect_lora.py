"""Compare LoRA weight magnitudes. alpha scalars are excluded -- they are
constants (1.0) and swamp the max. What matters is the size of the actual
lora_up/lora_down deltas: too large = the adjustment overwhelms the base model
and the image fries; near-zero = it learned nothing."""
import sys, pathlib
from safetensors import safe_open
import torch

LORA_DIR = pathlib.Path("tools/ComfyUI/models/loras")
for name in sys.argv[1:]:
    up, down, alpha = [], [], []
    with safe_open(str(LORA_DIR / name), framework="pt") as f:
        for k in f.keys():
            t = f.get_tensor(k).float()
            if "alpha" in k:
                alpha.append(float(t.reshape(-1)[0])); continue
            (up if "up" in k or "lora_B" in k else down).append(t)
    def stats(ts):
        if not ts: return "none"
        allw = torch.cat([t.reshape(-1) for t in ts])
        return (f"n={len(ts):<4} mean|w|={allw.abs().mean():.5f}  "
                f"max|w|={allw.abs().max():.4f}  std={allw.std():.5f}  "
                f"zeros={100.0*float((allw==0).sum())/allw.numel():.1f}%")
    print(f"{name}")
    print(f"   lora_down  {stats(down)}")
    print(f"   lora_up    {stats(up)}")
    print(f"   alpha      n={len(alpha)} value={alpha[0] if alpha else '-'}")
    if up and down:
        # effective delta scale: what actually gets added to the base weights
        prod = torch.cat([ (u.reshape(u.shape[0],-1).float().norm() *
                            d.reshape(d.shape[0],-1).float().norm()).reshape(1)
                           for u,d in zip(up,down) ])
        print(f"   delta scale  mean={prod.mean():.4f}  max={prod.max():.4f}")
