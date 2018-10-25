import unittest
from pyiron_base.core.settings.generic import Settings
import os

file_location = os.path.dirname(os.path.abspath(__file__))
s = Settings(config={'sql_file': os.path.join(file_location, 'vasprun.db'),
                     'project_paths': os.path.abspath(file_location),
                     'resource_paths': os.path.join(file_location, '../static')})

import posixpath
import numpy as np
from pyiron_vasp.vasprun import Vasprun, VasprunError

from pyiron_atomistics.structure.atoms import Atoms
from pyiron_dft.waves.electronic import ElectronicStructure

__author__ = "surendralal"


class TestVasprun(unittest.TestCase):

    """
    Testing the Vasprun() module.
    """

    def setUp(self):
        self.vp_list = list()
        direc = os.path.join(file_location, "../static/vasp_test_files/vasprun_samples")
        file_list = sorted(os.listdir(direc))
        del file_list[file_list.index("vasprun_spoilt.xml")]
        self.num_species = [3, 1, 2, 2, 3, 4]

        for f in file_list:
            vp = Vasprun()
            self.assertIsInstance(vp.vasprun_dict, dict)
            filename = posixpath.join(direc, f)
            vp.from_file(filename)
            self.vp_list.append(vp)
        vp = Vasprun()
        filename = posixpath.join(direc, "vasprun_spoilt.xml")
        self.assertRaises(VasprunError, vp.from_file, filename)

    def test_parse_generator(self):
        for vp in self.vp_list:
            self.assertIsInstance(vp.vasprun_dict["generator"], dict)
            self.assertTrue("program" in vp.vasprun_dict["generator"].keys())
            self.assertTrue("version" in vp.vasprun_dict["generator"].keys())
            self.assertTrue("time" in vp.vasprun_dict["generator"].keys())
            self.assertTrue("subversion" in vp.vasprun_dict["generator"].keys())
            self.assertTrue("platform" in vp.vasprun_dict["generator"].keys())
            self.assertTrue("date" in vp.vasprun_dict["generator"].keys())

    def test_parse_incar(self):
        for vp in self.vp_list:
            self.assertIsInstance(vp.vasprun_dict["incar"], dict)

    def test_parse_kpoints(self):
        for vp in self.vp_list:
            d = vp.vasprun_dict["kpoints"]
            self.assertIsInstance(d, dict)
            self.assertIsInstance(d["generation"], dict)
            if d["generation"]["scheme"] in ["Monkhorst-Pack"]:
                self.assertIsInstance(d["generation"]["divisions"], np.ndarray)
                self.assertIsInstance(d["generation"]["genvec"], np.ndarray)
                self.assertIsInstance(d["generation"]["shift"], np.ndarray)
                self.assertIsInstance(d["generation"]["usershift"], np.ndarray)
                self.assertTrue(len(d["generation"]["divisions"]) == 3)
                self.assertTrue(len(d["generation"]["genvec"]) == 3)
                self.assertTrue(len(d["generation"]["genvec"].T) == 3)
                self.assertTrue(len(d["generation"]["shift"]) == 3)
                self.assertTrue(len(d["generation"]["usershift"]) == 3)
            self.assertIsInstance(d["kpoint_list"], np.ndarray)
            self.assertIsInstance(d["kpoint_weights"], np.ndarray)
            self.assertEqual(len(d["kpoint_list"]), len(d["kpoint_weights"]))
            self.assertTrue(len(d["kpoint_list"].T) == 3)
            self.assertIsInstance(d["kpoint_weights"][-1], (float, np.float))

    def test_parse_atom_info(self):
        for vp in self.vp_list:
            d = vp.vasprun_dict["atominfo"]
            self.assertIsInstance(d, dict)
            self.assertIsInstance(d["species_dict"], dict)
            self.assertIsInstance(d["species_list"], list)
            n_atoms = 0
            for key, value in d["species_dict"].items():
                n_atoms += d["species_dict"][key]["n_atoms"]
            self.assertEqual(n_atoms, len(d["species_list"]))

    def test_parse_structure(self):
        for vp in self.vp_list:
            for pos_tag in ["init_structure", "final_structure"]:
                d = vp.vasprun_dict[pos_tag]
                self.assertIsInstance(d["positions"], np.ndarray)
                if "selective_dynamics" in d.keys():
                    self.assertIsInstance(d["selective_dynamics"], np.ndarray)

    def test_parse_sc_step(self):
        for vp in self.vp_list:
            d = vp.vasprun_dict
            self.assertIsInstance(d["scf_energies"], list)
            self.assertIsInstance(d["scf_dipole_moments"], list)

    def test_parse_calc(self):
        for vp in self.vp_list:
            d = vp.vasprun_dict
            self.assertIsInstance(d["positions"], np.ndarray)
            self.assertIsInstance(d["forces"], np.ndarray)
            self.assertIsInstance(d["cells"], np.ndarray)
            self.assertEqual(len(d["cells"]), len(d["positions"]))
            self.assertEqual(len(d["forces"]), len(d["positions"]))
            self.assertEqual(len(d["total_energies"]), len(d["positions"]))
            self.assertEqual(len(d["forces"]), len(d["scf_energies"]))
            self.assertEqual(len(d["forces"]), len(d["scf_dipole_moments"]))
            self.assertEqual(len(d["forces"].T), 3)
            self.assertEqual(len(d["positions"].T), 3)
            self.assertFalse(len(d["positions"][d["positions"] > 1.01]) > 0)
            self.assertFalse(np.max(d["positions"]) > 1.01)
            self.assertEqual(np.shape(d["cells"][0]), np.shape(np.eye(3)))
            self.assertIsInstance(d["grand_eigenvalue_matrix"], np.ndarray)
            self.assertIsInstance(d["grand_occupancy_matrix"], np.ndarray)
            self.assertEqual(np.shape(d["grand_occupancy_matrix"]), np.shape(d["grand_eigenvalue_matrix"]))
            [n_spin, n_kpts, n_bands] = np.shape(d["grand_occupancy_matrix"])
            self.assertEqual(len(d["kpoints"]["kpoint_list"]), n_kpts)
            self.assertEqual(len(d["kpoints"]["kpoint_list"]), n_kpts)
            self.assertGreaterEqual(n_spin, 1)
            self.assertGreaterEqual(n_bands, 1)

    def test_pdos_parser(self):
        for vp in self.vp_list:
            d = vp.vasprun_dict
            if "efermi" in d.keys():
                self.assertIsInstance(d["efermi"], float)
            if "grand_dos_matrix" in d.keys():
                [n_spin0, n_kpts0, n_bands0] = np.shape(d["grand_occupancy_matrix"])
                [n_spin, n_kpts, n_bands, n_atoms, n_orbitals] = np.shape(d["grand_dos_matrix"])
                self.assertEqual(len(d["kpoints"]["kpoint_list"]), n_kpts)
                self.assertEqual(len(d["positions"][0]), n_atoms)
                self.assertEqual(n_spin, n_spin0)
                self.assertEqual(n_bands, n_bands0)
                self.assertEqual(n_kpts, n_kpts0)
                self.assertIsInstance(d["grand_dos_matrix"], np.ndarray)
                self.assertIsInstance(d["orbital_dict"], dict)
                self.assertEqual(len(d["orbital_dict"].keys()), n_orbitals)

    def test_parse_parameters(self):
        for vp in self.vp_list:
            d = vp.vasprun_dict
            self.assertIsInstance(d, dict)

    def test_get_initial_structure(self):
        for vp in self.vp_list:
            basis = vp.get_initial_structure()
            self.assertIsInstance(basis, Atoms)
            self.assertTrue(np.max(basis.scaled_positions) < 1.01)

    def test_get_final_structure(self):
        for vp in self.vp_list:
            basis = vp.get_final_structure()
            self.assertIsInstance(basis, Atoms)
            self.assertTrue(np.max(basis.scaled_positions) < 1.01)
            self.assertFalse(np.max(basis.positions) < 1.01)

    def test_get_electronic_structure(self):
        for vp in self.vp_list:
            es_obj = vp.get_electronic_structure()
            self.assertIsInstance(es_obj, ElectronicStructure)
            if "grand_dos_matrix" in vp.vasprun_dict.keys():
                [_, n_kpts, n_bands, _, _] = np.shape(vp.vasprun_dict["grand_dos_matrix"])
                self.assertEqual(len(es_obj.kpoints), n_kpts)
                self.assertEqual(len(es_obj.kpoints[0].bands), n_bands)

    def test_species_info(self):
        for i, vp in enumerate(self.vp_list):
            self.assertEqual(len(vp.vasprun_dict["atominfo"]["species_dict"].keys()), self.num_species[i])
            self.assertEqual(vp.get_initial_structure().get_number_of_species(), self.num_species[i])
            self.assertEqual(vp.get_final_structure().get_number_of_species(), self.num_species[i])


if __name__ == '__main__':
    unittest.main()
