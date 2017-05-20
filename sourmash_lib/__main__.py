"""
sourmash command line.
"""
from __future__ import print_function
import sys
import argparse

from .logging import notify, error, set_quiet

from .commands import (categorize, compare, compute, dump, import_csv,
                       gather, index, sbt_combine, search,
                       plot, watch)

try:
    from sourmash_utils.__main__ import main as utils_main
    UTILS_AVAILABLE = True
except ImportError:
    UTILS_AVAILABLE = False


def main():
    set_quiet(False)

    commands = {'search': search, 'compute': compute,
                'compare': compare, 'plot': plot,
                'import_csv': import_csv, 'dump': dump,
                'index': index,
                'categorize': categorize, 'gather': gather,
                'watch': watch,
                'sbt_combine': sbt_combine}
    if UTILS_AVAILABLE:
        commands['utils'] = utils_main

    parser = argparse.ArgumentParser(
        description='work with RNAseq signatures',
        usage='''sourmash <command> [<args>]

Commands can be:

compute <filenames>         Compute MinHash signatures for sequences in files.
compare <filenames.sig>     Compute similarity matrix for multiple signatures.
search <query> <against>    Search a signature against a list of signatures.
plot <matrix>               Plot a distance matrix made by 'compare'.

Sequence Bloom Tree (SBT) utilities:

index                   Index a collection of signatures for fast searching.
sbt_combine             Combine multiple SBTs into a new one.
categorize              Identify best matches for many signatures using an SBT.
gather                  Search a metagenome signature for multiple
                              non-overlapping matches in the SBT.
watch                   Classify a stream of sequences.

Use '-h' to get subcommand-specific help, e.g.

sourmash compute -h
.
''')
    subparsers = parser.add_subparsers()

    for cmd in commands:
        subp = subparsers.add_parser(cmd)
        if cmd == 'compute':
            commands[cmd].add_args(subp)
            subp.set_defaults(cmd=commands[cmd])

    args = parser.parse_args()
    return args.cmd(**vars(args))
