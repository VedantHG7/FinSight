"""Run independently from the API: python -m app.worker."""
import logging
import time
from app.db.database import create_tables
from app.services.jobs import run_once
from app.check_runtime import check_runtime


def main():
    logging.basicConfig(level=logging.INFO)
    check_runtime()
    create_tables()
    logging.info('FinSight worker ready')
    while True:
        try:
            if not run_once():
                time.sleep(2)
        except KeyboardInterrupt:
            break
        except Exception:
            logging.exception('Worker iteration failed; retrying in 5 seconds')
            time.sleep(5)

if __name__ == '__main__':
    main()
