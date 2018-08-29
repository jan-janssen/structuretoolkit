"""
In contrast to many other tests, the non modal tests require a central database and can not be executed with the testing
configuration. Therefore these tests will use your default configuration.
"""
import os
from pyiron.project import Project
import unittest


def convergence_goal(self, **qwargs):
    import numpy as np
    eps = 0.2
    if "eps" in qwargs:
        eps = qwargs["eps"]
    erg_lst = self.get_from_childs("output/generic/energy")
    var = 1000 * np.var(erg_lst)
    print(var / len(erg_lst))
    if var / len(erg_lst) < eps:
        return True
    ham_prev = self[-1]
    job_name = self.first_child_name() + "_" + str(len(self))
    ham_next = ham_prev.restart(job_name=job_name)
    return ham_next

class TestMurnaghan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = Project('testing_murnaghan_non_modal')
        cls.basis = cls.project.create_structure(element="Fe", bravais_basis='bcc', lattice_constant=2.8)
        cls.project.remove_jobs(recursive=True)
        # cls.project.remove_jobs(recursive=True)
        # self.project.set_logging_level('INFO')

    @classmethod
    def tearDownClass(cls):
        project = Project('testing_murnaghan_non_modal')
        project.remove_jobs(recursive=True)
        project.remove(enable=True, enforce=True)

    def test_run(self):
        # Even though the test is completed successful
        ham = self.project.create_job(self.project.job_type.AtomisticExampleJob, "job_test")
        ham.structure = self.basis
        ham.server.run_mode.non_modal = True
        job_ser = self.project.create_job(self.project.job_type.SerialMaster, "murn_iter")
        job_ser.append(ham)
        job_ser.server.run_mode.non_modal = True
        job_ser.set_goal(convergence_goal, eps=0.4)
        murn = self.project.create_job("Murnaghan", "murnaghan")
        murn.ref_job = job_ser
        murn.input["num_points"] = 3
        murn.server.run_mode.non_modal = True
        murn.run()
        self.assertFalse(job_ser.status.finished)
        self.project.wait_for_job(murn, interval_in_s=5, max_iterations=250)
        self.assertTrue(murn.status.finished)
        murn.remove()
        job_ser.remove()
        self.project.remove(enable=True, enforce=True)


if __name__ == '__main__':
    unittest.main()
