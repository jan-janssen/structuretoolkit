# coding: utf-8
# Copyright (c) Max-Planck-Institut für Eisenforschung GmbH - Computational Materials Design (CM) Department
# Distributed under the terms of "New BSD License", see the LICENSE file.

import unittest
from ase.build import bulk
import structuretoolkit as stk


class TestMesh(unittest.TestCase):
    def test_mesh(self):
        structure = bulk("Al", cubic=True)
        self.assertEqual(stk.create_mesh(structure, n_mesh=4).shape, (3, 4, 4, 4))
        with self.assertRaises(ValueError):
            stk.create_mesh(structure, n_mesh=None, density=None)
        self.assertEqual(
            stk.create_mesh(
                structure, n_mesh=10, density=structure.cell[0, 0] / 4
            ).shape,
            (3, 10, 10, 10),
        )
        self.assertEqual(
            stk.create_mesh(
                structure, n_mesh=None, density=structure.cell[0, 0] / 4
            ).shape,
            (3, 4, 4, 4),
        )
        with assertRaises(ValueError):
            _ = stk.create_mesh(structure, n_mesh=[1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()