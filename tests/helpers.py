import threading
from concurrent.futures import ThreadPoolExecutor

from app.db.connection import connect


def run_concurrently(db_url: str, jobs: list) -> list:
    """Run every job in its own thread with its OWN database connection.

    All threads wait at a barrier and are released together, so the jobs really
    collide. Returns one outcome per job: None on success, or the exception raised.
    """
    barrier = threading.Barrier(len(jobs))

    def worker(job):
        conn = connect(db_url)
        try:
            barrier.wait(timeout=10)
            try:
                job(conn)
                return None
            except Exception as exc:        # we WANT to inspect failures
                return exc
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        return list(pool.map(worker, jobs))