"""I2C/GPIO business CLI. Use --batch for OPEN and transfers in one session."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexbridge_io import main
if __name__ == '__main__':
    raise SystemExit(main())
