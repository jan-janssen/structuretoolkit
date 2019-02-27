import unittest
import os
import posixpath
import numpy as np

from pyiron.atomistics.structure.atoms import Atoms
from pyiron.vasp.vasprun import Vasprun
from pyiron.dft.waves.dos import Dos
from pyiron.dft.waves.electronic import ElectronicStructure
from pyiron.base.generic.hdfio import FileHDFio
import sys

"""
@author: surendralal

Unittests for the pyiron.objects.electronic module
"""


class TestElectronicStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.es_list = list()
        cls.es_obj = ElectronicStructure()
        file_list = ["vasprun_1.xml", "vasprun_2.xml"]
        for f in file_list:
            vp = Vasprun()
            direc = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 "../../static/vasprun_samples"))
            filename = posixpath.join(direc, f)
            vp.from_file(filename)
            es = vp.get_electronic_structure()
            cls.es_list.append(es)

    @classmethod
    def tearDownClass(cls):
        if sys.version_info[0] >= 3:
            file_location = os.path.dirname(os.path.abspath(__file__))
            if os.path.isfile(os.path.join(file_location, "../../static/dft/test_es_hdf.h5")):
                os.remove(os.path.join(file_location, "../../static/dft/test_es_hdf.h5"))

    def test_init(self):
        for es in self.es_list:
            self.assertIsInstance(es, ElectronicStructure)
            self.assertIsInstance(es.eigenvalues, np.ndarray)
            self.assertIsInstance(es.occupancies, np.ndarray)
            self.assertEqual(np.shape(es.occupancy_matrix), np.shape(es.eigenvalue_matrix))
            if es.structure is not None:
                self.assertIsInstance(es.structure, Atoms)

    def test_add_kpoint(self):
        self.assertEqual(len(self.es_obj.kpoints), 0)
        self.es_obj.add_kpoint(value=[0., 0., 0.], weight=1.0)
        self.assertEqual(len(self.es_obj.kpoints), 1)

    def test_get_dos(self):
        for es in self.es_list:
            dos = es.get_dos()
            self.assertIsInstance(dos, Dos)

    def test_eigenvalues(self):
        for es in self.es_list:
            self.assertEqual(len(es.eigenvalues), np.product(np.shape(es.eigenvalue_matrix)))

    def test_occupancies(self):
        for es in self.es_list:
            self.assertEqual(len(es.occupancies), np.product(np.shape(es.occupancy_matrix)))

    def test_from_hdf(self):
        if sys.version_info[0] >= 3:
            filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../static/dft/es_hdf.h5")
            abs_filename = os.path.abspath(filename)
            hdf_obj = FileHDFio(abs_filename)
            es_obj_old = ElectronicStructure()
            es_obj_old.from_hdf_old(hdf_obj, "es_old")
            es_obj_new = ElectronicStructure()
            es_obj_new.from_hdf(hdf=hdf_obj, group_name="es_new")
            self.assertEqual(es_obj_old.efermi, es_obj_new.efermi)
            self.assertEqual(es_obj_old.is_metal, es_obj_new.is_metal)
            self.assertEqual(es_obj_old.vbm, es_obj_new.vbm)
            self.assertEqual(es_obj_old.cbm, es_obj_new.cbm)
            self.assertTrue(np.array_equal(es_obj_new.grand_dos_matrix, es_obj_old.grand_dos_matrix))

    def test_to_hdf(self):
        if sys.version_info[0] >= 3:
            filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../static/dft/test_es_hdf.h5")
            abs_filename = os.path.abspath(filename)
            hdf_obj = FileHDFio(abs_filename)
            es_obj_old = self.es_list[1]
            es_obj_old.to_hdf(hdf_obj, group_name="written_es")
            es_obj_new = ElectronicStructure()
            es_obj_new.from_hdf(hdf=hdf_obj, group_name="written_es")
            self.assertTrue(np.array_equal(hdf_obj["written_es/dos/grand_dos_matrix"], es_obj_old.grand_dos_matrix))
            self.assertEqual(es_obj_old.efermi, es_obj_new.efermi)
            self.assertEqual(es_obj_old.is_metal, es_obj_new.is_metal)
            self.assertEqual(es_obj_old.vbm, es_obj_new.vbm)
            self.assertEqual(es_obj_old.cbm, es_obj_new.cbm)
            self.assertTrue(np.array_equal(es_obj_new.grand_dos_matrix, es_obj_old.grand_dos_matrix))
            self.assertTrue(np.array_equal(es_obj_new.resolved_densities, es_obj_old.resolved_densities))

    def test_is_metal(self):
        self.assertTrue(self.es_list[1].is_metal)
