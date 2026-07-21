"""
conftest.py — adds chess-backend to sys.path so imports work without install.
"""
import sys
import os

# Add chess-backend directory to path
sys.path.insert(0, os.path.dirname(__file__))
# Add chess root directory to path (for engine imports in GameSession)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
