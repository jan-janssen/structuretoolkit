import os
import unittest
from pyiron.project import Project


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


class TestSerialMaster(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.file_location = os.path.dirname(os.path.abspath(__file__))
        cls.project = Project(os.path.join(cls.file_location, 'testing_serial'))
        cls.project.remove_jobs(recursive=True)

    @classmethod
    def tearDownClass(cls):
        file_location = os.path.dirname(os.path.abspath(__file__))
        project = Project(os.path.join(file_location, 'testing_serial'))
        project.remove(enable=True)

    def test_single_job(self):
        ham = self.project.create_job(self.project.job_type.ExampleJob, "job_single")
        job_ser = self.project.create_job(self.project.job_type.SerialMasterBase, "sequence_single")
        job_ser.append(ham)
        job_ser.run()
        self.assertTrue(job_ser.status.finished)
        self.assertTrue(job_ser[0].status.finished)
        self.assertEqual(len(job_ser), 1)
        job_ser.to_hdf()
        job_ser.remove()

    def test_multiple_jobs(self):
        job_ser = self.project.create_job(self.project.job_type.SerialMasterBase, "sequence_multi")
        ham = self.project.create_job(self.project.job_type.ExampleJob, "job_multi")
        job_ser.append(ham)
        job_ser.run()
        job_id = job_ser.job_id
        for i in range(1):
            job_ser_reload = self.project.load(job_id)
            ham = self.project.create_job(self.project.job_type.ExampleJob, "job_multi_" + str(i))
            job_ser_reload.append(ham)
            job_ser_reload.status.created = True
            job_ser_reload.run()
        self.assertTrue(job_ser_reload.status.finished)
        self.assertTrue(job_ser_reload[0].status.finished)
        self.assertTrue(job_ser_reload[1].status.finished)
        self.assertEqual(len(job_ser_reload), 2)
        job_ser.remove()

    def test_convergence_goal(self):
        ham = self.project.create_job(self.project.job_type.ExampleJob, "job_convergence")
        job_ser = self.project.create_job(self.project.job_type.SerialMasterBase, "sequence_convergence")
        job_ser.append(ham)
        job_ser.set_goal(convergence_goal=convergence_goal, eps=0.2)
        job_ser.run()
        self.assertTrue(job_ser.status.finished)
        self.assertTrue(len(job_ser) > 0)
        job_ser.remove()

    def test_single_job_new_hdf5(self):
        ham = self.project.create_job(self.project.job_type.ExampleJob, "job_single_nh")
        job_ser = self.project.create_job(self.project.job_type.SerialMasterBase, "sequence_single_nh")
        job_ser.server.new_hdf = False
        job_ser.append(ham)
        job_ser.run()
        self.assertTrue(job_ser.status.finished)
        self.assertTrue(job_ser[0].status.finished)
        self.assertEqual(len(job_ser), 1)
        job_ser.to_hdf()
        job_ser.remove()


if __name__ == '__main__':
    unittest.main()
