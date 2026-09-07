"""Production composition for the local multi-template render entrypoint."""

from __future__ import annotations

import threading
from typing import Any

from .multi_template_dispatcher import MultiTemplateRenderDispatcher
from .multi_template_illustrator_session import MultiTemplateIllustratorSession
from .multi_template_preflight import MultiTemplatePreflight
from .multi_template_render import MultiTemplateRenderService
from .multi_template_resolver import TemplateResolver
from .per_template_canary import PerTemplateCanaryRenderer
from .single_template_render_adapter import SingleTemplateRenderAdapter


def build_multi_template_render_service(
    client: Any,
    render_lock: threading.Lock,
    action_lock: threading.Lock,
) -> MultiTemplateRenderService:
    """Compose the additive workflow around the current single-template paths.

    The adapter deliberately owns the per-template production calls.  Therefore
    every group continues to use its existing department/manufacturer output
    policy, and only the parent-level collector adds a template namespace.
    """
    adapter = SingleTemplateRenderAdapter(
        central=client.central,
        cache=client.cache,
        data_dir=client.data_dir,
        v2_renderer=client.v2_renderer,
        font_dirs=client.font_dirs,
    )
    preflight = MultiTemplatePreflight(
        resolver=TemplateResolver(client.cache, client.central, v2_only=True),
        adapter=adapter,
    )
    dispatcher = MultiTemplateRenderDispatcher(
        jobs=client.jobs,
        group_renderer=adapter,
        canary_renderer=PerTemplateCanaryRenderer(adapter=adapter),
        render_lock=render_lock,
        illustrator_session_factory=MultiTemplateIllustratorSession,
        illustrator_session_binding=adapter.use_illustrator_session,
    )
    return MultiTemplateRenderService(
        preflight_runner=preflight,
        jobs=client.jobs,
        dispatcher=dispatcher,
        action_lock=action_lock,
    )


__all__ = ["build_multi_template_render_service"]
