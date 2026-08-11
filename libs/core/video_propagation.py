"""Qt-free interface for whole-video propagation backends."""


class PropagationBackend:
    """Stateless adapter implemented by portable and optional backends."""

    def propagate(self, request, direction, cancelled, emit_batch):
        """Return a final result while streaming immutable preview batches."""
        raise NotImplementedError
