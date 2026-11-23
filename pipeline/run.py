"""Run the whole pipeline: sources -> merge -> coverage -> site data.

python -m pipeline.run                 every active source (downloads what can be downloaded)
python -m pipeline.run --only us-oh    just these source ids (prefix match)
python -m pipeline.run --offline       rebuild from committed snapshots and rosters, no downloads
"""
import argparse

from pipeline import coverage, merge, sources


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', nargs='*')
    ap.add_argument('--offline', action='store_true')
    args = ap.parse_args(argv)
    sources.main([*(['--only', *args.only] if args.only else []), *(['--offline'] if args.offline else [])])
    merged = merge.build()
    print(f'Merged: {merged["counts"]}')
    cov = coverage.build()
    print(f'Coverage: {cov["totals"]["by_scope"]}; {len(cov["queue"])} sources in the queue.')


if __name__ == '__main__':
    main()
