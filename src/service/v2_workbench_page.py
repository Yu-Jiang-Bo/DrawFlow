"""Static HTML for the V2 template configuration workbench."""

from .v2_workbench_page_finish import PAGE_FINISH
from .v2_workbench_page_head import PAGE_HEAD
from .v2_workbench_page_main import PAGE_MAIN


INDEX_HTML = PAGE_HEAD + PAGE_MAIN + PAGE_FINISH
