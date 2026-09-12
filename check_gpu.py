import importlib.metadata as metadata
import json
import torch
import torch.nn.functional as F
import torchaudio

assert torch.__version__ == '2.8.0+cu126', torch.__version__
assert torchaudio.__version__ == '2.8.0+cu126', torchaudio.__version__
assert torch.version.cuda == '12.6'
assert torch.cuda.is_available()
assert torch.cuda.get_device_capability(0) == (6, 1)
for dtype in (torch.float32, torch.float16):
    x = torch.randn((32, 32), device='cuda', dtype=dtype)
    assert torch.isfinite(x @ x.T).all()
    q = torch.randn((1, 2, 16, 32), device='cuda', dtype=dtype)
    assert torch.isfinite(F.scaled_dot_product_attention(q, q, q)).all()
torch.cuda.synchronize()
print(json.dumps({'gpu': torch.cuda.get_device_name(0),
                  'capability': torch.cuda.get_device_capability(0),
                  'torch': torch.__version__, 'cuda': torch.version.cuda,
                  'architectures': torch.cuda.get_arch_list(),
                  'omnivoice': metadata.version('omnivoice'),
                  'wyoming': metadata.version('wyoming'),
                  'transformers': metadata.version('transformers'),
                  'matrix_and_attention_tests': 'passed'}))
