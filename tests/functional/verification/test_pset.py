from nagini_contracts.contracts import *


class A:
    pass


def test_pset() -> None:
    ints = PSet(1, 2, 3)
    four = PSet(4)
    a = A()
    ass = PSet(a)
    assert a in ass
    assert 3 in ints and 1 in ints
    assert 4 not in ints
    assert ass[0] is a
    assert len(ints) == 3
    ints2 = ints + ints
    assert len(ints2) == 3
    ints3 = ints + four
    assert len(ints3) == 4
    assert 4 in ints3
    assert 4 not in ints
    assert 4 not in ints2
    assert 1 in ints
    assert 1 in ints2
    assert 1 in ints3

    ints4 = ints3 - ints
    assert len(ints4) == 1
    assert 4 in ints4
    assert 1 not in ints4

    #:: ExpectedOutput(assert.failed:assertion.false)
    assert False
