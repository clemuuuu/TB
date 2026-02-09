from rich.console import Console
from rich.logging import RichHandler
import logging

console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)

log = logging.getLogger("tb")
