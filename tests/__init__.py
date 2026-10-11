import os
import sys

# Make the package importable when running: python3 -m unittest discover -s tests -t .
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
)
