from pathlib import Path
from dotenv import load_dotenv


project_root = Path(__file__).parent.parent.parent
load_dotenv(project_root / ".env")
