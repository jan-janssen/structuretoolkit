# coding: utf-8
# Copyright (c) Max-Planck-Institut für Eisenforschung GmbH - Computational Materials Design (CM) Department
# Distributed under the terms of "New BSD License", see the LICENSE file.

import unittest
import os
import posixpath
from pyiron.vasp.oszicar import Oszicar


class TestOszicar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.file_location = os.path.dirname(os.path.abspath(__file__))
        cls.file_list = list()
        cls.oszicar_parser = Oszicar()
        file_list = os.listdir(
            os.path.abspath(
                os.path.join(
                    cls.file_location, "../static/vasp_test_files/oszicar_samples"
                )
            )
        )
        for f in file_list:
            direc = os.path.abspath(
                os.path.join(
                    cls.file_location, "../static/vasp_test_files/oszicar_samples"
                )
            )
            filename = posixpath.join(direc, f)
            cls.file_list.append(filename)

    def test_energy_pot(self):
        for filename in self.file_list:
            self.oszicar_parser.from_file(filename=filename)
            if "1" in filename:
                energies = self.oszicar_parser.parse_dict["energy_pot"]
                self.assertTrue(all([energies[i] == val for i, val in enumerate([-17.7379867884])]))
            if "2" in filename:
                energies = self.oszicar_parser.parse_dict["energy_pot"]
                self.assertTrue(all([energies[i] == val for i, val in enumerate([-1166.23382927, -1166.07589814,
                                                                                 -1165.76905678, -1165.69531250,
                                                                                 -1165.85096438])]))
