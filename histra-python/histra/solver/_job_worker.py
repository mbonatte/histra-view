"""Private transport for jobs created by :mod:`histra.solver.parallel_jobs`."""
from pathlib import Path
import pickle
import sys

from histra.solver.parallel_jobs import _execute_job


def main() -> None:
    # Only the parent creates these private temporary files. Never accept an
    # untrusted pickle as a public job format.
    request, response = map(Path, sys.argv[1:])
    job = pickle.loads(request.read_bytes())
    response.write_bytes(pickle.dumps(_execute_job(job)))


if __name__ == "__main__":
    main()
