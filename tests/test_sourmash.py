"""
Tests for the 'sourmash' command line.
"""
from __future__ import print_function, unicode_literals
import os
import gzip
import shutil
import time
import screed
import glob
import json
import csv

from . import sourmash_tst_utils as utils
import sourmash_lib
from sourmash_lib import MinHash
from sourmash_lib.sbt import SBT
from sourmash_lib.sbtmh import SigLeaf
try:
    import matplotlib
    matplotlib.use('Agg')
except ImportError:
    pass

from sourmash_lib import signature
from sourmash_lib import VERSION

def test_run_sourmash():
    status, out, err = utils.runscript('sourmash', [], fail_ok=True)
    assert status != 0                    # no args provided, ok ;)


def test_run_sourmash_badcmd():
    status, out, err = utils.runscript('sourmash', ['foobarbaz'], fail_ok=True)
    assert status != 0                    # bad arg!
    assert "Unrecognized command" in err

def test_sourmash_info():
    status, out, err = utils.runscript('sourmash', ['info'], fail_ok=False)

    # no output to stdout
    assert not out
    assert "sourmash version" in err
    assert "loaded from path" in err
    assert VERSION in err


def test_sourmash_info_verbose():
    status, out, err = utils.runscript('sourmash', ['info', '-v'])

    # no output to stdout
    assert not out
    assert "khmer version" in err
    assert "screed version" in err
    assert "loaded from path" in err


def test_do_sourmash_compute():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', testdata1],
                                           in_directory=location)

        sigfile = os.path.join(location, 'short.fa.sig')
        assert os.path.exists(sigfile)

        sig = next(signature.load_signatures(sigfile))
        assert sig.name().endswith('short.fa')


def test_do_sourmash_compute_output_valid_file():
    """ Trigger bug #123 """
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        testdata3 = utils.get_test_data('short3.fa')
        sigfile = os.path.join(location, 'short.fa.sig')

        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', '-o', sigfile,
                                            testdata1,
                                            testdata2, testdata3],
                                           in_directory=location)

        assert os.path.exists(sigfile)
        assert not out # stdout should be empty

        # is it valid json?
        with open(sigfile, 'r') as f:
            data = json.load(f)

        filesigs = [sig['filename'] for sig in data]
        assert all(testdata in filesigs
                   for testdata in (testdata1, testdata2, testdata3))


def test_do_sourmash_compute_output_stdout_valid():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        testdata3 = utils.get_test_data('short3.fa')

        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', '-o', '-',
                                            testdata1,
                                            testdata2, testdata3],
                                           in_directory=location)

        # is it valid json?
        data = json.loads(out)

        filesigs = [sig['filename'] for sig in data]
        assert all(testdata in filesigs
                   for testdata in (testdata1, testdata2, testdata3))


def test_do_sourmash_compute_output_and_name_valid_file():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        testdata3 = utils.get_test_data('short3.fa')
        sigfile = os.path.join(location, 'short.fa.sig')

        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', '-o', sigfile,
                                            '--merge', '"name"',
                                            testdata1,
                                            testdata2, testdata3],
                                           in_directory=location)

        assert os.path.exists(sigfile)

        # is it valid json?
        import json
        with open(sigfile, 'r') as f:
            data = json.load(f)

        assert len(data) == 1

        all_testdata = " ".join([testdata1, testdata2, testdata3])
        sigfile_merged = os.path.join(location, 'short.all.fa.sig')
        cmd = "cat {} | {}/sourmash compute -k 31 -o {} -".format(
                all_testdata, utils.scriptpath(), sigfile_merged)
        status, out, err = utils.run_shell_cmd(cmd, in_directory=location)

        with open(sigfile_merged, 'r') as f:
            data_merged = json.load(f)

        assert data[0]['signatures'][0]['mins'] == data_merged[0]['signatures'][0]['mins']


def test_do_sourmash_compute_singleton():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', '--singleton',
                                            testdata1],
                                           in_directory=location)

        sigfile = os.path.join(location, 'short.fa.sig')
        assert os.path.exists(sigfile)

        sig = next(signature.load_signatures(sigfile))
        assert sig.name().endswith('shortName')


def test_do_sourmash_compute_name():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', '--merge', 'foo',
                                            testdata1, '-o', 'foo.sig'],
                                           in_directory=location)

        sigfile = os.path.join(location, 'foo.sig')
        assert os.path.exists(sigfile)

        sig = next(signature.load_signatures(sigfile))
        assert sig.name() == 'foo'

        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', '--name', 'foo',
                                            testdata1, '-o', 'foo2.sig'],
                                           in_directory=location)

        sigfile2 = os.path.join(location, 'foo2.sig')
        assert os.path.exists(sigfile)

        sig2 = next(signature.load_signatures(sigfile))
        assert sig2.name() == 'foo'
        assert sig.name() == sig2.name()


def test_do_sourmash_compute_name_fail_no_output():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', '--merge', 'foo',
                                            testdata1],
                                           in_directory=location,
                                           fail_ok=True)
        assert status == -1


def test_do_sourmash_compute_merge_fail_no_output():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', '--merge', 'foo',
                                            testdata1],
                                           in_directory=location,
                                           fail_ok=True)
        assert status == -1

        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', '--name', 'foo',
                                            testdata1],
                                           in_directory=location,
                                           fail_ok=True)
        assert status == -1


def test_do_sourmash_compute_name_from_first():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short3.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', '--name-from-first',
                                            testdata1],
                                           in_directory=location)

        sigfile = os.path.join(location, 'short3.fa.sig')
        assert os.path.exists(sigfile)

        sig = next(signature.load_signatures(sigfile))
        assert sig.name() == 'firstname'


def test_do_sourmash_compute_multik():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21,31',
                                            testdata1],
                                           in_directory=location)
        outfile = os.path.join(location, 'short.fa.sig')
        assert os.path.exists(outfile)

        siglist = list(signature.load_signatures(outfile))
        assert len(siglist) == 2
        ksizes = set([ x.minhash.ksize for x in siglist ])
        assert 21 in ksizes
        assert 31 in ksizes


def test_do_sourmash_compute_multik_with_protein():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21,30',
                                            '--protein',
                                            testdata1],
                                           in_directory=location)
        outfile = os.path.join(location, 'short.fa.sig')
        assert os.path.exists(outfile)

        with open(outfile, 'rt') as fp:
            sigdata = fp.read()
            siglist = list(signature.load_signatures(sigdata))
            assert len(siglist) == 4
            ksizes = set([ x.minhash.ksize for x in siglist ])
            assert 21 in ksizes
            assert 30 in ksizes


def test_do_sourmash_compute_multik_with_nothing():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21,31',
                                            '--no-protein', '--no-dna',
                                            testdata1],
                                           in_directory=location,
                                           fail_ok=True)
        outfile = os.path.join(location, 'short.fa.sig')
        assert not os.path.exists(outfile)


def test_do_sourmash_compute_multik_protein_bad_ksize():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '20,32',
                                            '--protein', '--no-dna',
                                            testdata1],
                                           in_directory=location,
                                           fail_ok=True)
        outfile = os.path.join(location, 'short.fa.sig')
        assert not os.path.exists(outfile)
        assert 'protein ksizes must be divisible by 3' in err


def test_do_sourmash_compute_multik_only_protein():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21,30',
                                            '--protein', '--no-dna',
                                            testdata1],
                                           in_directory=location)
        outfile = os.path.join(location, 'short.fa.sig')
        assert os.path.exists(outfile)

        with open(outfile, 'rt') as fp:
            sigdata = fp.read()
            siglist = list(signature.load_signatures(sigdata))
            assert len(siglist) == 2
            ksizes = set([ x.minhash.ksize for x in siglist ])
            assert 21 in ksizes
            assert 30 in ksizes


def test_do_sourmash_compute_multik_input_is_protein():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('ecoli.faa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21,30',
                                            '--input-is-protein',
                                            testdata1],
                                           in_directory=location)
        outfile = os.path.join(location, 'ecoli.faa.sig')
        assert os.path.exists(outfile)

        with open(outfile, 'rt') as fp:
            sigdata = fp.read()
            siglist = list(signature.load_signatures(sigdata))
            assert len(siglist) == 2
            ksizes = set([ x.minhash.ksize for x in siglist ])
            assert 21 in ksizes
            assert 30 in ksizes

            moltype = set([ x.minhash.is_molecule_type('protein')
                            for x in siglist ])
            assert len(moltype) == 1
            assert True in moltype


def test_do_sourmash_compute_multik_outfile():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        outfile = os.path.join(location, 'FOO.xxx')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21,31',
                                            testdata1, '-o', outfile],
                                           in_directory=location)
        assert os.path.exists(outfile)

        siglist = list(signature.load_signatures(outfile))
        assert len(siglist) == 2
        ksizes = set([ x.minhash.ksize for x in siglist ])
        assert 21 in ksizes
        assert 31 in ksizes


def test_do_sourmash_compute_with_scaled_1():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        outfile = os.path.join(location, 'FOO.xxx')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21,31',
                                            '--scaled', '1',
                                            testdata1, '-o', outfile],
                                            in_directory=location)
        assert os.path.exists(outfile)

        siglist = list(signature.load_signatures(outfile))
        assert len(siglist) == 2

        max_hashes = [ x.minhash.max_hash for x in siglist ]
        assert len(max_hashes) == 2
        assert set(max_hashes) == { sourmash_lib.MAX_HASH }


def test_do_sourmash_compute_with_scaled_2():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        outfile = os.path.join(location, 'FOO.xxx')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21,31',
                                            '--scaled', '2',
                                            testdata1, '-o', outfile],
                                            in_directory=location)
        assert os.path.exists(outfile)

        siglist = list(signature.load_signatures(outfile))
        assert len(siglist) == 2

        max_hashes = [ x.minhash.max_hash for x in siglist ]
        assert len(max_hashes) == 2
        assert set(max_hashes) == set([ int(2**64 /2.) ])


def test_do_sourmash_compute_with_scaled():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        outfile = os.path.join(location, 'FOO.xxx')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21,31',
                                            '--scaled', '100',
                                            testdata1, '-o', outfile],
                                            in_directory=location)
        assert os.path.exists(outfile)

        siglist = list(signature.load_signatures(outfile))
        assert len(siglist) == 2

        max_hashes = [ x.minhash.max_hash for x in siglist ]
        assert len(max_hashes) == 2
        assert set(max_hashes) == set([ int(2**64 /100.) ])


def test_do_sourmash_compute_with_bad_scaled():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        outfile = os.path.join(location, 'FOO.xxx')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21,31',
                                            '--scaled', '-1',
                                            testdata1, '-o', outfile],
                                            in_directory=location,
                                            fail_ok=True)

        assert status != 0
        assert '--scaled value must be >= 1' in err

        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21,31',
                                            '--scaled', '1000.5',
                                            testdata1, '-o', outfile],
                                            in_directory=location,
                                            fail_ok=True)

        assert status != 0
        assert '--scaled value must be integer value' in err

        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21,31',
                                            '--scaled', '1e9',
                                            testdata1, '-o', outfile],
                                            in_directory=location)

        assert status == 0
        assert 'WARNING: scaled value is nonsensical!?' in err


def test_do_sourmash_compute_with_seed():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        outfile = os.path.join(location, 'FOO.xxx')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21,31',
                                            '--seed', '43',
                                            testdata1, '-o', outfile],
                                            in_directory=location)
        assert os.path.exists(outfile)

        siglist = list(signature.load_signatures(outfile))
        assert len(siglist) == 2

        seeds = [ x.minhash.seed for x in siglist ]
        assert len(seeds) == 2
        assert set(seeds) == set([ 43 ])


def test_do_sourmash_check_protein_comparisons():
    # this test checks 2 x 2 protein comparisons with E. coli genes.
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('ecoli.faa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21',
                                            '--input-is-protein',
                                            '--singleton',
                                            testdata1],
                                           in_directory=location)
        sig1 = os.path.join(location, 'ecoli.faa.sig')
        assert os.path.exists(sig1)

        testdata2 = utils.get_test_data('ecoli.genes.fna')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21',
                                            '--protein', '--no-dna',
                                            '--singleton',
                                            testdata2],
                                           in_directory=location)
        sig2 = os.path.join(location, 'ecoli.genes.fna.sig')
        assert os.path.exists(sig2)

        # I'm not sure why load_signatures is randomizing order, but ok.
        x = list(signature.load_signatures(sig1))
        sig1_aa, sig2_aa = sorted(x, key=lambda x: x.name())

        x = list(signature.load_signatures(sig2))
        sig1_trans, sig2_trans = sorted(x, key=lambda x: x.name())

        name1 = sig1_aa.name().split()[0]
        assert name1 == 'NP_414543.1'
        name2 = sig2_aa.name().split()[0]
        assert name2 == 'NP_414544.1'
        name3 = sig1_trans.name().split()[0]
        assert name3 == 'gi|556503834:2801-3733'
        name4 = sig2_trans.name().split()[0]
        assert name4 == 'gi|556503834:337-2799'

        print(name1, name3, round(sig1_aa.similarity(sig1_trans), 3))
        print(name2, name3, round(sig2_aa.similarity(sig1_trans), 3))
        print(name1, name4, round(sig1_aa.similarity(sig2_trans), 3))
        print(name2, name4, round(sig2_aa.similarity(sig2_trans), 3))

        assert round(sig1_aa.similarity(sig1_trans), 3) == 0.0
        assert round(sig2_aa.similarity(sig1_trans), 3) == 0.166
        assert round(sig1_aa.similarity(sig2_trans), 3) == 0.174
        assert round(sig2_aa.similarity(sig2_trans), 3) == 0.0


def test_do_sourmash_check_knowngood_dna_comparisons():
    # this test checks against a known good signature calculated
    # by utils/compute-dna-mh-another-way.py
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('ecoli.genes.fna')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21',
                                            '--singleton', '--dna',
                                            testdata1],
                                           in_directory=location)
        sig1 = os.path.join(location, 'ecoli.genes.fna.sig')
        assert os.path.exists(sig1)

        x = list(signature.load_signatures(sig1))
        sig1, sig2 = sorted(x, key=lambda x: x.name())

        knowngood = utils.get_test_data('benchmark.dna.sig')
        good = list(signature.load_signatures(knowngood))[0]

        assert sig2.similarity(good) == 1.0


def test_do_sourmash_check_knowngood_input_protein_comparisons():
    # this test checks against a known good signature calculated
    # by utils/compute-input-prot-another-way.py
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('ecoli.faa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21',
                                            '--input-is-protein',
                                            '--singleton',
                                            testdata1],
                                           in_directory=location)
        sig1 = os.path.join(location, 'ecoli.faa.sig')
        assert os.path.exists(sig1)

        x = list(signature.load_signatures(sig1))
        sig1_aa, sig2_aa = sorted(x, key=lambda x: x.name())

        knowngood = utils.get_test_data('benchmark.input_prot.sig')
        good_aa = list(signature.load_signatures(knowngood))[0]

        assert sig1_aa.similarity(good_aa) == 1.0


def test_do_sourmash_check_knowngood_protein_comparisons():
    # this test checks against a known good signature calculated
    # by utils/compute-prot-mh-another-way.py
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('ecoli.genes.fna')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21',
                                            '--singleton', '--protein',
                                            '--no-dna',
                                            testdata1],
                                           in_directory=location)
        sig1 = os.path.join(location, 'ecoli.genes.fna.sig')
        assert os.path.exists(sig1)

        x = list(signature.load_signatures(sig1))
        sig1_trans, sig2_trans = sorted(x, key=lambda x: x.name())

        knowngood = utils.get_test_data('benchmark.prot.sig')
        good_trans = list(signature.load_signatures(knowngood))[0]

        assert sig2_trans.similarity(good_trans) == 1.0


def test_do_compare_quiet():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31',
                                            testdata1, testdata2],
                                           in_directory=location)


        status, out, err = utils.runscript('sourmash',
                                           ['compare', 'short.fa.sig',
                                            'short2.fa.sig', '--csv', 'xxx',
                                            '-q'],
                                           in_directory=location)
        assert not out
        assert not err


def test_do_compare_output_csv():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', testdata1, testdata2],
                                           in_directory=location)


        status, out, err = utils.runscript('sourmash',
                                           ['compare', 'short.fa.sig',
                                            'short2.fa.sig', '--csv', 'xxx'],
                                           in_directory=location)

        with open(os.path.join(location, 'xxx')) as fp:
            lines = fp.readlines()
            assert len(lines) == 3
            assert lines[1:] == ['1.0,0.93\n', '0.93,1.0\n']


def test_do_compare_downsample():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '--scaled', '200',
                                            '-k', '31', testdata1],
                                           in_directory=location)


        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '--scaled', '100',
                                            '-k', '31', testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['compare', 'short.fa.sig',
                                            'short2.fa.sig', '--csv', 'xxx'],
                                           in_directory=location)

        print(status, out, err)
        assert 'downsampling to scaled value of 200' in err
        with open(os.path.join(location, 'xxx')) as fp:
            lines = fp.readlines()
            assert len(lines) == 3
            assert lines[1].startswith('1.0,0.6666')
            assert lines[2].startswith('0.6666')


def test_do_compare_output_multiple_k():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21', testdata1],
                                           in_directory=location)
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['compare', 'short.fa.sig',
                                            'short2.fa.sig', '--csv', 'xxx'],
                                           in_directory=location,
                                           fail_ok=True)

        print(status, out, err)

        assert status == -1
        assert 'multiple k-mer sizes loaded; please specify one' in err
        assert '(saw k-mer sizes 21, 31)' in err


def test_do_compare_output_multiple_moltype():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21', '--dna', testdata1],
                                           in_directory=location)
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '21', '--protein', testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['compare', 'short.fa.sig',
                                            'short2.fa.sig', '--csv', 'xxx'],
                                           in_directory=location,
                                           fail_ok=True)

        assert status == -1
        assert 'multiple molecule types loaded;' in err


def test_do_plot_comparison():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', testdata1, testdata2],
                                           in_directory=location)


        status, out, err = utils.runscript('sourmash',
                                           ['compare', 'short.fa.sig',
                                            'short2.fa.sig', '-o', 'cmp'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash', ['plot', 'cmp'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, "cmp.dendro.png"))
        assert os.path.exists(os.path.join(location, "cmp.matrix.png"))


def test_do_plot_comparison_2():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', testdata1, testdata2],
                                           in_directory=location)


        status, out, err = utils.runscript('sourmash',
                                           ['compare', 'short.fa.sig',
                                            'short2.fa.sig', '-o', 'cmp'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['plot', 'cmp', '--pdf'],
                                           in_directory=location)
        assert os.path.exists(os.path.join(location, "cmp.dendro.pdf"))
        assert os.path.exists(os.path.join(location, "cmp.matrix.pdf"))


def test_do_plot_comparison_3():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', testdata1, testdata2],
                                           in_directory=location)


        status, out, err = utils.runscript('sourmash',
                                           ['compare', 'short.fa.sig',
                                            'short2.fa.sig', '-o', 'cmp'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['plot', 'cmp', '--labels'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, "cmp.dendro.png"))
        assert os.path.exists(os.path.join(location, "cmp.matrix.png"))


def test_plot_subsample_1():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('genome-s10.fa.gz.sig')
        testdata2 = utils.get_test_data('genome-s11.fa.gz.sig')
        testdata3 = utils.get_test_data('genome-s12.fa.gz.sig')
        testdata4 = utils.get_test_data('genome-s10+s11.sig')
        inp_sigs = [testdata1, testdata2, testdata3, testdata4]

        status, out, err = utils.runscript('sourmash',
                                           ['compare'] + inp_sigs + \
                                           ['-o', 'cmp', '-k', '21', '--dna'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['plot', 'cmp',
                                            '--subsample', '3'],
                                           in_directory=location)

        print(out)

        expected = """\
0\ts10+s11
1\tgenome-s12.fa.gz
2\tgenome-s10.fa.gz"""
        assert expected in out


def test_plot_subsample_2():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('genome-s10.fa.gz.sig')
        testdata2 = utils.get_test_data('genome-s11.fa.gz.sig')
        testdata3 = utils.get_test_data('genome-s12.fa.gz.sig')
        testdata4 = utils.get_test_data('genome-s10+s11.sig')
        inp_sigs = [testdata1, testdata2, testdata3, testdata4]

        status, out, err = utils.runscript('sourmash',
                                           ['compare'] + inp_sigs + \
                                           ['-o', 'cmp', '-k', '21', '--dna'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['plot', 'cmp',
                                            '--subsample', '3',
                                            '--subsample-seed=2'],
                                           in_directory=location)

        print(out)
        expected = """\
0\tgenome-s12.fa.gz
1\ts10+s11
2\tgenome-s11.fa.gz"""
        assert expected in out


def test_search_sig_does_not_exist():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', testdata1],
                                           in_directory=location)



        status, out, err = utils.runscript('sourmash',
                                           ['search', 'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location, fail_ok=True)

        print(status, out, err)
        assert status == -1
        assert 'does not exist' in err


def test_search():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', testdata1, testdata2],
                                           in_directory=location)



        status, out, err = utils.runscript('sourmash',
                                           ['search', 'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)
        print(status, out, err)
        assert '1 matches' in out
        assert '93.0%' in out


def test_search_csv():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', testdata1, testdata2],
                                           in_directory=location)



        status, out, err = utils.runscript('sourmash',
                                           ['search', 'short.fa.sig',
                                            'short2.fa.sig', '-o', 'xxx.csv'],
                                           in_directory=location)
        print(status, out, err)

        csv_file = os.path.join(location, 'xxx.csv')

        with open(csv_file) as fp:
            reader = csv.DictReader(fp)
            row = next(reader)
            assert float(row['similarity']) == 0.93
            assert row['name'].endswith('short2.fa')
            assert row['filename'].endswith('short2.fa.sig')
            assert row['md5'] == '914591cd1130aa915fe0c0c63db8f19d'


def test_compare_deduce_molecule():
    # deduce DNA vs protein from query, if it is unique
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '30',
                                            '--no-dna', '--protein',
                                            testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['compare', 'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)
        print(status, out, err)
        assert 'min similarity in matrix: 0.91' in out


def test_compare_choose_molecule_dna():
    # choose molecule type
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '30',
                                            '--dna', '--protein',
                                            testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['compare', '--dna', 'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)
        print(status, out, err)
        assert 'min similarity in matrix: 0.938' in out


def test_compare_choose_molecule_protein():
    # choose molecule type
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '30',
                                            '--dna', '--protein',
                                            testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['compare', '--protein', 'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)
        print(status, out, err)
        assert 'min similarity in matrix: 0.91' in out


def test_compare_no_choose_molecule_fail():
    # choose molecule type
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '30',
                                            '--dna', '--protein',
                                            testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['compare', 'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location,
                                           fail_ok=True)

        assert 'multiple molecule types loaded; please specify' in err
        assert status != 0


def test_compare_deduce_ksize():
    # deduce ksize, if it is unique
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '29',
                                            testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['compare', 'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)
        print(status, out, err)
        assert 'min similarity in matrix: 0.938' in out


def test_search_deduce_molecule():
    # deduce DNA vs protein from query, if it is unique
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '30',
                                            '--no-dna', '--protein',
                                            testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['search', 'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)
        print(status, out, err)
        assert '1 matches' in out
        assert '(k=30, protein)' in err


def test_search_deduce_ksize():
    # deduce ksize from query, if it is unique
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '23',
                                            testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['search', 'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)
        print(status, out, err)
        assert '1 matches' in out
        assert 'k=23' in err


def test_do_sourmash_sbt_search_output():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', 'zzz', '-k', '31',
                                            'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['search', 'short.fa.sig',
                                            'zzz', '-o', 'foo'],
                                           in_directory=location)
        outfile = open(os.path.join(location, 'foo'))
        output = outfile.read()
        print(output)
        assert 'short.fa' in output
        assert 'short2.fa' in output


def test_search_deduce_ksize_and_select_appropriate():
    # deduce ksize from query and select correct signature from DB
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '24',
                                            testdata1],
                                           in_directory=location)
        # The DB contains signatres for multiple ksizes
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '23,24',
                                            testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['search', 'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)
        print(status, out, err)
        assert '1 matches' in out
        assert 'k=24' in err


def test_search_deduce_ksize_not_unique():
    # deduce ksize from query, fail because it is not unique
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '23,25',
                                            testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['search', 'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location,
                                           fail_ok=True)
        print(status, out, err)
        assert status == -1
        assert '2 signatures matching ksize' in err


def test_search_deduce_ksize_vs_user_specified():
    # user specified ksize is not available
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '23',
                                            testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['search', '-k', '24',
                                            'short.fa.sig', 'short2.fa.sig'],
                                           in_directory=location,
                                           fail_ok=True)
        print(status, out, err)
        assert status == -1
        assert '0 signatures matching ksize' in err


def test_search_containment():
    # search with --containment in signatures
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2],
                                           in_directory=location)



        status, out, err = utils.runscript('sourmash',
                                           ['search', 'short.fa.sig',
                                            'short2.fa.sig', '--containment'],
                                           in_directory=location)
        print(status, out, err)
        assert '1 matches' in out
        assert '95.8%' in out


def test_search_containment_sbt():
    # search with --containment in an SBT
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2],
                                           in_directory=location)



        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz',
                                            'short2.fa.sig'],
                                           in_directory=location)


        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))
        status, out, err = utils.runscript('sourmash',
                                           ['search', 'short.fa.sig',
                                            'zzz', '--containment'],
                                           in_directory=location)
        print(status, out, err)
        assert '1 matches' in out
        assert '95.8%' in out


def test_search_gzip():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2],
                                           in_directory=location)

        data = open(os.path.join(location, 'short.fa.sig'), 'rb').read()
        with gzip.open(os.path.join(location, 'zzz.gz'), 'wb') as fp:
            fp.write(data)

        data = open(os.path.join(location, 'short2.fa.sig'), 'rb').read()
        with gzip.open(os.path.join(location, 'yyy.gz'), 'wb') as fp:
            fp.write(data)

        status, out, err = utils.runscript('sourmash',
                                           ['search', 'zzz.gz',
                                            'yyy.gz'],
                                           in_directory=location)
        print(status, out, err)
        assert '1 matches' in out
        assert '93.0%' in out


def test_search_2():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        testdata3 = utils.get_test_data('short3.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2,
                                            testdata3],
                                           in_directory=location)



        status, out, err = utils.runscript('sourmash',
                                           ['search', 'short.fa.sig',
                                            'short2.fa.sig', 'short3.fa.sig'],
                                           in_directory=location)
        print(status, out, err)
        assert '2 matches' in out
        assert '93.0%' in out
        assert '89.6%' in out


def test_search_3():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        testdata3 = utils.get_test_data('short3.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2,
                                            testdata3],
                                           in_directory=location)



        status, out, err = utils.runscript('sourmash',
                                           ['search', '-n', '1',
                                            'short.fa.sig',
                                            'short2.fa.sig', 'short3.fa.sig'],
                                           in_directory=location)
        print(status, out, err)
        assert '2 matches; showing first 1' in out


def test_search_metagenome():
    with utils.TempDirectory() as location:
        testdata_glob = utils.get_test_data('gather/GCF*.sig')
        testdata_sigs = glob.glob(testdata_glob)

        query_sig = utils.get_test_data('gather/combined.sig')

        cmd = ['index', 'gcf_all', '-k', '21']
        cmd.extend(testdata_sigs)

        status, out, err = utils.runscript('sourmash', cmd,
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'gcf_all.sbt.json'))

        cmd = 'search {} gcf_all -k 21'.format(query_sig)
        status, out, err = utils.runscript('sourmash', cmd.split(' '),
                                           in_directory=location)

        print(out)
        print(err)

        assert ' 33.2%       NC_003198.1 Salmonella enterica subsp. enterica serovar T...' in out
        assert '12 matches; showing first 3:' in out


def test_search_metagenome_downsample():
    with utils.TempDirectory() as location:
        testdata_glob = utils.get_test_data('gather/GCF*.sig')
        testdata_sigs = glob.glob(testdata_glob)

        query_sig = utils.get_test_data('gather/combined.sig')

        cmd = ['index', 'gcf_all', '-k', '21']
        cmd.extend(testdata_sigs)

        status, out, err = utils.runscript('sourmash', cmd,
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'gcf_all.sbt.json'))

        cmd = 'search {} gcf_all -k 21 --scaled 100000'.format(query_sig)
        status, out, err = utils.runscript('sourmash', cmd.split(' '),
                                           in_directory=location)

        print(out)
        print(err)

        assert ' 32.9%       NC_003198.1 Salmonella enterica subsp. enterica serovar T...' in out
        assert '12 matches; showing first 3:' in out


def test_search_metagenome_downsample_containment():
    with utils.TempDirectory() as location:
        testdata_glob = utils.get_test_data('gather/GCF*.sig')
        testdata_sigs = glob.glob(testdata_glob)

        query_sig = utils.get_test_data('gather/combined.sig')

        cmd = ['index', 'gcf_all', '-k', '21']
        cmd.extend(testdata_sigs)

        status, out, err = utils.runscript('sourmash', cmd,
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'gcf_all.sbt.json'))

        cmd = 'search {} gcf_all -k 21 --scaled 100000 --containment'
        cmd = cmd.format(query_sig)
        status, out, err = utils.runscript('sourmash', cmd.split(' '),
                                           in_directory=location)

        print(out)
        print(err)

        assert ' 32.9%       NC_003198.1 Salmonella enterica subsp. enterica serovar T...' in out
        assert '12 matches; showing first 3:' in out


def test_mash_csv_to_sig():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa.msh.dump')
        testdata2 = utils.get_test_data('short.fa')

        status, out, err = utils.runscript('sourmash', ['import_csv',
                                                        testdata1,
                                                        '-o', 'xxx.sig'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31',
                                            '-n', '970', testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['search', '-k', '31',
                                            'short.fa.sig', 'xxx.sig'],
                                           in_directory=location)
        print(status, out, err)
        assert '1 matches:' in out
        assert '100.0%       short.fa' in out


def test_do_sourmash_index_bad_args():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz',
                                            'short.fa.sig',
                                            'short2.fa.sig',
                                            '--dna', '--protein'],
                                           in_directory=location, fail_ok=True)

        assert "cannot specify both --dna and --protein!" in err
        assert status != 0


def test_do_sourmash_sbt_search():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz',
                                            'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['search', 'short.fa.sig',
                                            'zzz'],
                                           in_directory=location)
        print(out)

        assert 'short.fa' in out
        assert 'short2.fa' in out


def test_do_sourmash_sbt_search_wrong_ksize():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2,
                                            '-k', '31,51'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz',
                                            'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['search', '-k', '51',
                                            'short.fa.sig', 'zzz'],
                                           in_directory=location,
                                           fail_ok=True)

        assert status == -1
        assert 'this is different from' in err


def test_do_sourmash_sbt_search_multiple():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz',
                                            'short.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz2',
                                            'short2.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz2.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['search', 'short.fa.sig',
                                            'zzz', 'zzz2'],
                                           in_directory=location)
        print(out)

        assert 'short.fa' in out
        assert 'short2.fa' in out


def test_do_sourmash_sbt_search_and_sigs():
    # search an SBT and a signature at same time.
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz',
                                            'short.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['search', 'short.fa.sig',
                                            'zzz', 'short2.fa.sig'],
                                           in_directory=location)
        print(out)

        assert 'short.fa' in out
        assert 'short2.fa' in out


def test_do_sourmash_sbt_search_downsample():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2,
                                            '--scaled=10'],
                                           in_directory=location)

        testdata1 = utils.get_test_data('short.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1,
                                            '--scaled=5', '-o', 'query.sig'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz',
                                            'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['search', 'query.sig', 'zzz'],
                                           in_directory=location)
        print(out)

        assert 'short.fa' in out
        assert 'short2.fa' in out


def test_do_sourmash_index_single():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz',
                                            'short.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['search', 'short.fa.sig',
                                            'zzz'],
                                           in_directory=location)
        print(out)

        assert 'short.fa' in out


def test_do_sourmash_sbt_search_selectprot():
    # index should fail when run on signatures with multiple types
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')

        args = ['compute', testdata1, testdata2,
                '--protein', '--dna', '-k', '30']
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)

        args = ['index', '-k', '31', 'zzz', 'short.fa.sig', 'short2.fa.sig']
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location, fail_ok=True)

        print(out)
        print(err)
        assert status != 0


def test_do_sourmash_sbt_search_dnaprotquery():
    # sbt_search should fail if non-single query sig given
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')

        args = ['compute', testdata1, testdata2,
                '--protein', '--dna', '-k', '30']
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)

        args = ['index', 'zzz', '--protein', 'short.fa.sig',
                'short2.fa.sig']
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        args = ['search', 'short.fa.sig', 'zzz']
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location, fail_ok=True)
        assert status != 0
        print(out)
        print(err)
        assert 'need exactly one' in err


def test_do_sourmash_index_traverse():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz',
                                            '--traverse-dir', '.'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))
        assert 'loaded 2 sigs; saving SBT under' in err

        status, out, err = utils.runscript('sourmash',
                                           ['search', 'short.fa.sig',
                                            'zzz'],
                                           in_directory=location)
        print(out)

        assert 'short.fa' in out
        assert 'short2.fa' in out


def test_do_sourmash_index_sparseness():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz',
                                            '--traverse-dir', '.',
                                            '--sparseness', '1.0'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))
        assert 'loaded 2 sigs; saving SBT under' in err

        status, out, err = utils.runscript('sourmash',
                                           ['search', 'short.fa.sig',
                                            'zzz'],
                                           in_directory=location)
        print(out)

        assert len(glob.glob(os.path.join(location, '.sbt.zzz', '*'))) == 2
        assert not glob.glob(os.path.join(location, '.sbt.zzz', '*internal*'))

        assert 'short.fa' in out
        assert 'short2.fa' in out


def test_do_sourmash_sbt_combine():
    with utils.TempDirectory() as location:
        files = [utils.get_test_data(f) for f in utils.SIG_FILES]

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz'] + files,
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['sbt_combine', 'joined',
                                            'zzz.sbt.json', 'zzz.sbt.json'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'joined.sbt.json'))

        filename = os.path.splitext(os.path.basename(utils.SIG_FILES[0]))[0]

        status, out, err = utils.runscript('sourmash',
                                           ['search', files[0], 'zzz'],
                                           in_directory=location)
        print(out)

        # we get notification of signature loading, too - so notify + result.
        assert out.count(filename) == 1

        status, out, err = utils.runscript('sourmash',
                                           ['search', files[0], 'joined'],
                                           in_directory=location)
        print(out)

        assert out.count(filename) == 1


def test_do_sourmash_index_append():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        testdata3 = utils.get_test_data('short3.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2, testdata3],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz',
                                            'short.fa.sig', 'short2.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        sbt_name = os.path.join(location, 'zzz',)
        sig_loc = os.path.join(location, 'short3.fa.sig')
        status, out, err = utils.runscript('sourmash',
                                           ['search', sig_loc, sbt_name])
        print(out)

        assert 'short.fa' in out
        assert 'short2.fa' in out
        assert 'short3.fa' not in out

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', '--append',
                                            'zzz',
                                            'short3.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        sbt_name = os.path.join(location, 'zzz',)
        sig_loc = os.path.join(location, 'short3.fa.sig')
        status, out, err = utils.runscript('sourmash',
                                           ['search',
                                            '--threshold', '0.95',
                                            sig_loc, sbt_name])
        print(out)

        assert 'short.fa' not in out
        assert 'short2.fa' in out
        assert 'short3.fa' in out


def test_do_sourmash_sbt_search_otherdir():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'xxx/zzz',
                                            'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'xxx', 'zzz.sbt.json'))

        sbt_name = os.path.join(location,'xxx', 'zzz',)
        sig_loc = os.path.join(location, 'short.fa.sig')
        status, out, err = utils.runscript('sourmash',
                                           ['search', sig_loc, sbt_name])
        print(out)

        assert 'short.fa' in out
        assert 'short2.fa' in out


def test_do_sourmash_sbt_search_bestonly():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz',
                                            'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['search', '--best-only',
                                            'short.fa.sig', 'zzz'],
                                           in_directory=location)
        print(out)

        assert 'short.fa' in out


def test_compare_with_abundance_1():
    with utils.TempDirectory() as location:
        # create two signatures
        E1 = MinHash(ksize=5, n=5, is_protein=False,
                        track_abundance=True)
        E2 = MinHash(ksize=5, n=5, is_protein=False,
                        track_abundance=True)

        E1.add_sequence('ATGGA')
        E2.add_sequence('ATGGA')

        s1 = signature.SourmashSignature('', E1, filename='e1', name='e1')
        s2 = signature.SourmashSignature('', E2, filename='e2', name='e2')

        signature.save_signatures([s1],
                                  open(os.path.join(location, 'e1.sig'), 'w'))
        signature.save_signatures([s2],
                                  open(os.path.join(location, 'e2.sig'), 'w'))

        status, out, err = utils.runscript('sourmash',
                                           ['search', 'e1.sig', 'e2.sig',
                                            '-k' ,'5'],
                                           in_directory=location)
        assert '100.0%' in out


def test_compare_with_abundance_2():
    with utils.TempDirectory() as location:
        # create two signatures
        E1 = MinHash(ksize=5, n=5, is_protein=False,
                        track_abundance=True)
        E2 = MinHash(ksize=5, n=5, is_protein=False,
                        track_abundance=True)

        E1.add_sequence('ATGGA')

        E1.add_sequence('ATGGA')
        E2.add_sequence('ATGGA')

        s1 = signature.SourmashSignature('', E1, filename='e1', name='e1')
        s2 = signature.SourmashSignature('', E2, filename='e2', name='e2')

        signature.save_signatures([s1],
                                  open(os.path.join(location, 'e1.sig'), 'w'))
        signature.save_signatures([s2],
                                  open(os.path.join(location, 'e2.sig'), 'w'))

        status, out, err = utils.runscript('sourmash',
                                           ['search', 'e1.sig', 'e2.sig',
                                            '-k' ,'5'],
                                           in_directory=location)
        assert '100.0%' in out


def test_compare_with_abundance_3():
    with utils.TempDirectory() as location:
        # create two signatures
        E1 = MinHash(ksize=5, n=5, is_protein=False,
                        track_abundance=True)
        E2 = MinHash(ksize=5, n=5, is_protein=False,
                        track_abundance=True)

        E1.add_sequence('ATGGA')
        E1.add_sequence('GGACA')

        E1.add_sequence('ATGGA')
        E2.add_sequence('ATGGA')

        s1 = signature.SourmashSignature('', E1, filename='e1', name='e1')
        s2 = signature.SourmashSignature('', E2, filename='e2', name='e2')

        signature.save_signatures([s1],
                                  open(os.path.join(location, 'e1.sig'), 'w'))
        signature.save_signatures([s2],
                                  open(os.path.join(location, 'e2.sig'), 'w'))

        status, out, err = utils.runscript('sourmash',
                                           ['search', 'e1.sig', 'e2.sig',
                                            '-k' ,'5'],
                                           in_directory=location)
        assert '70.5%' in out


def test_gather():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2,
                                            '--scaled', '10'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata2,
                                            '--scaled', '10',
                                            '-o', 'query.fa.sig'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz',
                                            'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['gather',
                                            'query.fa.sig', 'zzz', '-o',
                                            'foo.csv', '--threshold-bp=1'],
                                           in_directory=location)

        print(out)
        print(err)

        assert '0.9 kbp     100.0%  100.0%' in out


def test_gather_csv():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2,
                                            '--scaled', '10'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata2,
                                            '--scaled', '10',
                                            '-o', 'query.fa.sig'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz',
                                            'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['gather',
                                            'query.fa.sig', 'zzz', '-o',
                                            'foo.csv', '--threshold-bp=1'],
                                           in_directory=location)

        print(out)
        print(err)

        csv_file = os.path.join(location, 'foo.csv')

        with open(csv_file) as fp:
            reader = csv.DictReader(fp)
            row = next(reader)
            print(row)
            assert float(row['intersect_bp']) == 910
            assert float(row['f_orig_query']) == 1.0
            assert float(row['f_unique_to_query']) == 1.0
            assert float(row['f_match']) == 1.0
            assert row['name'].endswith('short2.fa')
            assert row['filename'] == 'zzz'
            assert row['md5'] == 'c9d5a795eeaaf58e286fb299133e1938'


def test_gather_multiple_sbts():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2,
                                            '--scaled', '10'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata2,
                                            '--scaled', '10',
                                            '-o', 'query.fa.sig'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', 'zzz', '-k', '31',
                                            'short.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['index', 'zzz2', '-k', '31',
                                            'short2.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['gather',
                                            'query.fa.sig', 'zzz', 'zzz2',
                                            '-o', 'foo.csv',
                                            '--threshold-bp=1'],
                                           in_directory=location)

        print(out)
        print(err)

        assert '0.9 kbp     100.0%  100.0%' in out


def test_gather_sbt_and_sigs():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', testdata1, testdata2,
                                            '--scaled', '10'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata2,
                                            '--scaled', '10',
                                            '-o', 'query.fa.sig'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz',
                                            'short.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['gather',
                                            'query.fa.sig', 'zzz', 'short2.fa.sig',
                                            '-o', 'foo.csv',
                                            '--threshold-bp=1'],
                                           in_directory=location)

        print(out)
        print(err)

        assert '0.9 kbp     100.0%  100.0%' in out


def test_gather_file_output():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2,
                                            '--scaled', '10'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata2,
                                            '--scaled', '10',
                                            '-o', 'query.fa.sig'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', '-k', '31', 'zzz',
                                            'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['gather',
                                            'query.fa.sig', 'zzz',
                                            '--threshold-bp=500',
                                            '-o', 'foo.out'],
                                           in_directory=location)

        print(out)
        print(err)
        assert '0.9 kbp     100.0%  100.0%' in out
        with open(os.path.join(location, 'foo.out')) as f:
            output = f.read()
            print((output,))
            assert '910,1.0,1.0' in output


def test_gather_metagenome():
    with utils.TempDirectory() as location:
        testdata_glob = utils.get_test_data('gather/GCF*.sig')
        testdata_sigs = glob.glob(testdata_glob)

        query_sig = utils.get_test_data('gather/combined.sig')

        cmd = ['index', 'gcf_all', '-k', '21']
        cmd.extend(testdata_sigs)

        status, out, err = utils.runscript('sourmash', cmd,
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'gcf_all.sbt.json'))

        cmd = 'gather {} gcf_all -k 21'.format(query_sig)
        status, out, err = utils.runscript('sourmash', cmd.split(' '),
                                           in_directory=location)

        print(out)
        print(err)

        assert 'found 12 matches total' in out
        assert 'the recovered matches hit 100.0% of the query' in out
        assert '4.9 Mbp      33.2%  100.0%      NC_003198.1 Salmonella enterica subsp...' in out
        assert '4.7 Mbp      32.1%    1.5%      NC_011294.1 Salmonella enterica subsp...' in out


def test_gather_metagenome_output_unassigned():
    with utils.TempDirectory() as location:
        testdata_glob = utils.get_test_data('gather/GCF_000195995*g')
        testdata_sigs = glob.glob(testdata_glob)[0]

        query_sig = utils.get_test_data('gather/combined.sig')

        cmd = 'gather {} {} -k 21'.format(query_sig, testdata_sigs)
        cmd += ' --output-unassigned=unassigned.sig'
        status, out, err = utils.runscript('sourmash', cmd.split(' '),
                                           in_directory=location)

        print(out)
        print(err)

        assert 'found 1 matches total' in out
        assert 'the recovered matches hit 33.2% of the query' in out
        assert '4.9 Mbp      33.2%  100.0%      NC_003198.1 Salmonella enterica subsp...' in out

        # now examine unassigned
        testdata2_glob = utils.get_test_data('gather/GCF_000009505.1*.sig')
        testdata2_sigs = glob.glob(testdata2_glob)[0]

        cmd = 'gather {} {} -k 21'.format('unassigned.sig', testdata2_sigs)
        status, out, err = utils.runscript('sourmash', cmd.split(' '),
                                           in_directory=location)

        print(out)
        print(err)
        assert '1.3 Mbp      13.6%   28.2%      NC_011294.1 Salmonella enterica subsp...' in out


def test_gather_metagenome_downsample():
    with utils.TempDirectory() as location:
        testdata_glob = utils.get_test_data('gather/GCF*.sig')
        testdata_sigs = glob.glob(testdata_glob)

        query_sig = utils.get_test_data('gather/combined.sig')

        cmd = ['index', 'gcf_all', '-k', '21']
        cmd.extend(testdata_sigs)

        status, out, err = utils.runscript('sourmash', cmd,
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'gcf_all.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['gather', query_sig, 'gcf_all',
                                            '-k', '21', '--scaled', '100000'],
                                           in_directory=location)

        print(out)
        print(err)

        assert 'found 11 matches total' in out
        assert 'the recovered matches hit 100.0% of the query' in out
        assert '5.2 Mbp      32.9%  100.0%      NC_003198.1 Salmonella enterica subsp...' in out
        assert any(('4.1 Mbp      25.9%    2.4%      NC_011294.1 Salmonella enterica subsp...' in out,
                    '4.1 Mbp      25.9%    2.4%      NC_011274.1 Salmonella enterica subsp...' in out))


def test_gather_save_matches():
    with utils.TempDirectory() as location:
        testdata_glob = utils.get_test_data('gather/GCF*.sig')
        testdata_sigs = glob.glob(testdata_glob)

        query_sig = utils.get_test_data('gather/combined.sig')

        cmd = ['index', 'gcf_all', '-k', '21']
        cmd.extend(testdata_sigs)

        status, out, err = utils.runscript('sourmash', cmd,
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'gcf_all.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['gather', query_sig, 'gcf_all',
                                            '-k', '21',
                                            '--save-matches', 'save.sigs'],
                                           in_directory=location)

        print(out)
        print(err)

        assert 'found 12 matches total' in out
        assert 'the recovered matches hit 100.0% of the query' in out
        assert os.path.exists(os.path.join(location, 'save.sigs'))


def test_gather_error_no_cardinality_query():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', testdata1, testdata2],
                                           in_directory=location)

        testdata3 = utils.get_test_data('short3.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', '-k', '31', testdata3],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', 'zzz',
                                            'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['gather',
                                            'short3.fa.sig', 'zzz'],
                                           in_directory=location,
                                           fail_ok=True)
        assert status == -1
        assert "query signature needs to be created with --scaled" in err


def test_gather_deduce_ksize():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2,
                                            '--scaled', '10', '-k', '23'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata2,
                                            '--scaled', '10', '-k', '23',
                                            '-o', 'query.fa.sig'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', 'zzz',
                                            'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['gather', 'query.fa.sig', 'zzz',
                                            '--threshold-bp=1'],
                                           in_directory=location)

        print(out)
        print(err)

        assert '0.9 kbp     100.0%  100.0%' in out


def test_gather_deduce_moltype():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('short.fa')
        testdata2 = utils.get_test_data('short2.fa')
        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata1, testdata2,
                                            '--scaled', '10', '-k', '30',
                                            '--no-dna', '--protein'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['compute', testdata2,
                                            '--scaled', '10', '-k', '30',
                                            '--no-dna', '--protein',
                                            '-o', 'query.fa.sig'],
                                           in_directory=location)

        status, out, err = utils.runscript('sourmash',
                                           ['index', 'zzz',
                                            'short.fa.sig',
                                            'short2.fa.sig'],
                                           in_directory=location)

        assert os.path.exists(os.path.join(location, 'zzz.sbt.json'))

        status, out, err = utils.runscript('sourmash',
                                           ['gather', 'query.fa.sig', 'zzz',
                                            '--threshold-bp=1'],
                                           in_directory=location)

        print(out)
        print(err)

        assert '1.9 kbp     100.0%  100.0%' in out


def test_sbt_categorize():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('genome-s10.fa.gz.sig')
        testdata2 = utils.get_test_data('genome-s11.fa.gz.sig')
        testdata3 = utils.get_test_data('genome-s12.fa.gz.sig')
        testdata4 = utils.get_test_data('genome-s10+s11.sig')

        shutil.copyfile(testdata1, os.path.join(location, '1.sig'))
        shutil.copyfile(testdata2, os.path.join(location, '2.sig'))
        shutil.copyfile(testdata3, os.path.join(location, '3.sig'))
        shutil.copyfile(testdata4, os.path.join(location, '4.sig'))

        # omit 3
        args = ['index', '--dna', '-k', '21', 'zzz', '1.sig', '2.sig']
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)

        args = ['categorize', 'zzz', '--traverse-directory', '.',
                '--ksize', '21', '--dna', '--csv', 'out.csv']
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)

        print(out)
        print(err)

        # mash dist genome-s10.fa.gz genome-s10+s11.fa.gz
        # yields 521/1000 ==> ~0.5
        assert 'for s10+s11, found: 0.50 genome-s10.fa.gz' in err

        out_csv = open(os.path.join(location, 'out.csv')).read()
        assert './4.sig,genome-s10.fa.gz,0.50' in out_csv


def test_sbt_categorize_already_done():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('genome-s10.fa.gz.sig')
        testdata2 = utils.get_test_data('genome-s11.fa.gz.sig')
        testdata3 = utils.get_test_data('genome-s12.fa.gz.sig')
        testdata4 = utils.get_test_data('genome-s10+s11.sig')

        shutil.copyfile(testdata1, os.path.join(location, '1.sig'))
        shutil.copyfile(testdata2, os.path.join(location, '2.sig'))
        shutil.copyfile(testdata3, os.path.join(location, '3.sig'))
        shutil.copyfile(testdata4, os.path.join(location, '4.sig'))

        # omit 3
        args = ['index', '--dna', '-k', '21', 'zzz', '1.sig', '2.sig']
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)

        with open(os.path.join(location, 'in.csv'), 'wt') as fp:
            fp.write('./4.sig,genome-s10.fa.gz,0.50')

        args = ['categorize', 'zzz', './2.sig', './4.sig',
                '--ksize', '21', '--dna', '--load-csv', 'in.csv']
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)

        print(out)
        print(err)
        assert 'for genome-s11.fa.gz, no match found'
        assert not 'for s10+s11, found: 0.50 genome-s10.fa.gz' in err


def test_sbt_categorize_already_done_traverse():
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('genome-s10.fa.gz.sig')
        testdata2 = utils.get_test_data('genome-s11.fa.gz.sig')
        testdata3 = utils.get_test_data('genome-s12.fa.gz.sig')
        testdata4 = utils.get_test_data('genome-s10+s11.sig')

        shutil.copyfile(testdata1, os.path.join(location, '1.sig'))
        shutil.copyfile(testdata2, os.path.join(location, '2.sig'))
        shutil.copyfile(testdata3, os.path.join(location, '3.sig'))
        shutil.copyfile(testdata4, os.path.join(location, '4.sig'))

        # omit 3
        args = ['index', '--dna', '-k', '21', 'zzz', '1.sig', '2.sig']
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)

        with open(os.path.join(location, 'in.csv'), 'wt') as fp:
            fp.write('./4.sig,genome-s10.fa.gz,0.50')

        args = ['categorize', 'zzz', '--traverse-directory', '.',
                '--ksize', '21', '--dna', '--load-csv', 'in.csv']
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)

        print(out)
        print(err)
        assert 'for genome-s11.fa.gz, no match found'
        assert not 'for s10+s11, found: 0.50 genome-s10.fa.gz' in err


def test_sbt_categorize_multiple_ksizes_moltypes():
    # 'categorize' should fail when there are multiple ksizes or moltypes
    # present
    with utils.TempDirectory() as location:
        testdata1 = utils.get_test_data('genome-s10.fa.gz.sig')
        testdata2 = utils.get_test_data('genome-s11.fa.gz.sig')
        testdata3 = utils.get_test_data('genome-s12.fa.gz.sig')

        shutil.copyfile(testdata1, os.path.join(location, '1.sig'))
        shutil.copyfile(testdata2, os.path.join(location, '2.sig'))
        shutil.copyfile(testdata3, os.path.join(location, '3.sig'))

        args = ['index', '--dna', '-k', '21', 'zzz', '1.sig', '2.sig']
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)

        args = ['categorize', 'zzz', '--traverse-directory', '.']
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location, fail_ok=True)

        assert status != 0
        assert 'multiple k-mer sizes/molecule types present' in err


def test_watch():
    with utils.TempDirectory() as location:
        testdata0 = utils.get_test_data('genome-s10.fa.gz')
        testdata1 = utils.get_test_data('genome-s10.fa.gz.sig')
        shutil.copyfile(testdata1, os.path.join(location, '1.sig'))

        args = ['index', '--dna', '-k', '21', 'zzz', '1.sig']
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)

        cmd = """

             gunzip -c {} | {}/sourmash watch --ksize 21 --dna zzz

        """.format(testdata0, utils.scriptpath())
        status, out, err = utils.run_shell_cmd(cmd, in_directory=location)

        print(out)
        print(err)
        assert 'FOUND: genome-s10.fa.gz, at 1.000' in out


def test_watch_deduce_ksize():
    with utils.TempDirectory() as location:
        testdata0 = utils.get_test_data('genome-s10.fa.gz')
        utils.runscript('sourmash',
                        ['compute', testdata0, '-k', '29', '-o', '1.sig'],
                        in_directory=location)

        args = ['index', '--dna', '-k', '29', 'zzz', '1.sig']
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)

        cmd = """

             gunzip -c {} | {}/sourmash watch --dna zzz

        """.format(testdata0, utils.scriptpath())
        status, out, err = utils.run_shell_cmd(cmd, in_directory=location)

        print(out)
        print(err)
        assert 'Computing signature for k=29' in err
        assert 'genome-s10.fa.gz, at 1.000' in out


def test_watch_coverage():
    with utils.TempDirectory() as location:
        testdata0 = utils.get_test_data('genome-s10.fa.gz')
        testdata1 = utils.get_test_data('genome-s10.fa.gz.sig')
        shutil.copyfile(testdata1, os.path.join(location, '1.sig'))

        args = ['index', '--dna', '-k', '21', 'zzz', '1.sig']
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)

        with open(os.path.join(location, 'query.fa'), 'wt') as fp:
            record = list(screed.open(testdata0))[0]
            for start in range(0, len(record), 100):
                fp.write('>{}\n{}\n'.format(start,
                                            record.sequence[start:start+500]))

        args = ['watch', '--ksize', '21', '--dna', 'zzz', 'query.fa']
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)

        print(out)
        print(err)
        assert 'FOUND: genome-s10.fa.gz, at 1.000' in out


def test_storage_convert():
    import pytest
    pytest.importorskip('ipfsapi')

    with utils.TempDirectory() as location:
        testdata = utils.get_test_data('v2.sbt.json')
        shutil.copyfile(testdata, os.path.join(location, 'v2.sbt.json'))
        shutil.copytree(os.path.join(os.path.dirname(testdata), '.sbt.v2'),
                        os.path.join(location, '.sbt.v2'))
        testsbt = os.path.join(location, 'v2.sbt.json')

        original = SBT.load(testsbt, leaf_loader=SigLeaf.load)

        args = ['storage', 'convert', '-b', 'ipfs', testsbt]
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)

        ipfs = SBT.load(testsbt, leaf_loader=SigLeaf.load)

        assert len(original.nodes) == len(ipfs.nodes)
        assert all(n1[1].name == n2[1].name
                   for (n1, n2) in zip(sorted(original.nodes.items()),
                                       sorted(ipfs.nodes.items())))

        args = ['storage', 'convert',
                '-b', """'TarStorage("{}")'""".format(
                    os.path.join(location, 'v2.sbt.tar.gz')),
                testsbt]
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)
        tar = SBT.load(testsbt, leaf_loader=SigLeaf.load)

        assert len(original.nodes) == len(tar.nodes)
        assert all(n1[1].name == n2[1].name
                   for (n1, n2) in zip(sorted(original.nodes.items()),
                                       sorted(tar.nodes.items())))

def test_storage_convert_identity():
    import pytest
    pytest.importorskip('ipfsapi')

    with utils.TempDirectory() as location:
        testdata = utils.get_test_data('v2.sbt.json')
        shutil.copyfile(testdata, os.path.join(location, 'v2.sbt.json'))
        shutil.copytree(os.path.join(os.path.dirname(testdata), '.sbt.v2'),
                        os.path.join(location, '.sbt.v2'))
        testsbt = os.path.join(location, 'v2.sbt.json')

        original = SBT.load(testsbt, leaf_loader=SigLeaf.load)

        args = ['storage', 'convert', '-b', 'fsstorage', testsbt]
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)

        identity = SBT.load(testsbt, leaf_loader=SigLeaf.load)

        assert len(original.nodes) == len(identity.nodes)
        assert all(n1[1].name == n2[1].name
                   for (n1, n2) in zip(sorted(original.nodes.items()),
                                       sorted(identity.nodes.items())))


def test_storage_convert_fsstorage_newpath():
    import pytest
    pytest.importorskip('ipfsapi')

    with utils.TempDirectory() as location:
        testdata = utils.get_test_data('v2.sbt.json')
        shutil.copyfile(testdata, os.path.join(location, 'v2.sbt.json'))
        shutil.copytree(os.path.join(os.path.dirname(testdata), '.sbt.v2'),
                        os.path.join(location, '.sbt.v2'))
        testsbt = os.path.join(location, 'v2.sbt.json')

        original = SBT.load(testsbt, leaf_loader=SigLeaf.load)

        args = ['storage', 'convert',
                           '-b', 'fsstorage({})'.format(os.path.join(location, 'v3')),
                           testsbt]
        status, out, err = utils.runscript('sourmash', args,
                                           in_directory=location)

        identity = SBT.load(testsbt, leaf_loader=SigLeaf.load)

        assert len(original.nodes) == len(identity.nodes)
        assert all(n1[1].name == n2[1].name
                   for (n1, n2) in zip(sorted(original.nodes.items()),
                                       sorted(identity.nodes.items())))
