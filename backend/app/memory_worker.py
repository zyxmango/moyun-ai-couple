"""独立长期记忆 Worker：python -m app.memory_worker"""
from .services.memory_jobs import run_worker


if __name__ == "__main__":
    run_worker()
