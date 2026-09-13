"""Optional upstream FlashInfer acceleration with a bounded CUDA graph cache."""
from collections import OrderedDict


class GraphCache(OrderedDict):
    def __init__(self, limit):
        super().__init__()
        self.limit = limit

    def get(self, key, default=None):
        if key in self:
            self.move_to_end(key)
        return super().get(key, default)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > self.limit:
            self.popitem(last=False)


def enable_flashinfer(model, cuda_graph=False, cache_size=4):
    from omnivoice.models.omnivoice_flashinfer import apply_flashinfer
    apply_flashinfer(model, enable_cuda_graph=cuda_graph)
    model._fi_graph_cache = GraphCache(cache_size)
