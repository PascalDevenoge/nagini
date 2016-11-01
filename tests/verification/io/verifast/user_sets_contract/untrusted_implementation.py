from py2viper_contracts.contracts import (
    ContractOnly,
    Ensures,
    Import,
    Requires,
    Result,
)
from py2viper_contracts.io import *
from verifast.stdio_simple import (
    putchar,
)

from verifast.user_sets_contract.specification import (
    example_io,
    Interface,
)


class Implementation(Interface):

    def main(self, t1: Place) -> Place:
        IOExists1(Place)(
            lambda t2: (
                Requires(
                    token(t1, 2) and
                    example_io(t1, t2)
                ),
                Ensures(
                    token(t2) and
                    t2 == Result()
                ),
            )
        )
        Open(example_io(t1))
        success, t2 = putchar('h', t1)
        success, t3 = putchar('i', t2)
        return t3
