ZopStopper (/watch/) data built from the public sources by `MUNI=stellenbosch` (fetch_muni.py, build_money.py, build_muni.py).
The deploy workflow uses it when it is newer than the data workflow's saved copy (cache key good-muni-*). Once the data workflow
runs with the current code, its copy is newer and this file is not used; it can then be deleted.
