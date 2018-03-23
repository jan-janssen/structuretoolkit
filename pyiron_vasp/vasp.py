# coding: utf-8
# Copyright (c) Max-Planck-Institut für Eisenforschung GmbH - Computational Materials Design (CM) Department
# Distributed under the terms of "New BSD License", see the LICENSE file.

from __future__ import print_function
import os
import posixpath
import subprocess
import numpy as np
import tables

from pyiron_dft.generic import GenericDFTJob
from pyiron_vasp.potential import VaspPotentialFile
from pyiron_atomistics.structure.atoms import Atoms, CrystalStructure
from pyironbase.core.settings.generic import Settings
from pyironbase.objects.generic.parameters import GenericParameters
from pyiron_atomistics.md_analysis.trajectory_analysis import unwrap_coordinates
from pyiron_vasp.outcar import Outcar
from pyiron_vasp.procar import Procar
from pyiron_vasp.structure import read_atoms, write_poscar, vasp_sorter
from pyiron_vasp.vasprun import Vasprun as Vr
from pyiron_vasp.vasprun import VasprunError
from pyiron_vasp.volumetric_data import VaspVolumetricData
from pyiron_dft.waves.electronic import ElectronicStructure

__author__ = "Sudarsan Surendralal"
__copyright__ = "Copyright 2017, Max-Planck-Institut für Eisenforschung GmbH - " \
                "Computational Materials Design (CM) Department"
__version__ = "1.0"
__maintainer__ = "Sudarsan Surendralal"
__email__ = "surendralal@mpie.de"
__status__ = "production"
__date__ = "Sep 1, 2017"

s = Settings()


class Vasp(GenericDFTJob):
    """
    Class to setup and run and analyze VASP simulations which is a derivative of pyiron.objects.job.generic.GenericJob.
    The functions in these modules are written in such the function names and attributes are very generic
    (get_structure(), molecular_dynamics(), version) but the functions are written to handle VASP specific input/output.

    Args:
        project (pyiron.project.Project instance):  Specifies the project path among other attributes
        job_name (str): Name of the job

    Attributes:
        input (pyiron_vasp.vasp.Input instance): Instance which handles the input
        output (pyiron_vasp.vasp.Input instance): Instance which handles the output

    Examples:

        Let's say you need to run a vasp simulation where you would like to control the input parameters manually. To
        set up a static dft run with Gaussian smearing and a k-point MP mesh of [6, 6, 6]. You would have to set it up
        as shown below:

        >>> ham = Vasp(job_name="trial_job")
        >>> ham.input.incar.set(IBRION=-1)
        >>> ham.input.incar.set(ISMEAR=0)
        >>> ham.input.kpoints.set(size_of_mesh=[6, 6, 6])

        However, the according to pyiron's philosophy, it is recommended to avoid using code specific tags like IBRION,
        ISMEAR etc. Therefore the recommended way to set this calculation is as follows:

        >>> ham = Vasp(job_name="trial_job")
        >>> ham.calc_static()
        >>> ham.set_occupancy_smearing(smearing="gaussian")
        >>> ham.set_kpoints(mesh=[6, 6, 6])

        The exact same tags as in the first examples are set automatically.
    """

    def __init__(self, project, job_name):
        super(Vasp, self).__init__(project, job_name)
        self.__name__ = "Vasp"
        self.__version__ = None  # Reset the version number to the executable is set automatically
        self._sorted_indices = None
        self._executable_activate()
        self.input = Input()
        self.input.incar["SYSTEM"] = self.job_name
        self.output = Output()

    @property
    def plane_wave_cutoff(self):
        return self.input.incar['ENCUT']

    @plane_wave_cutoff.setter
    def plane_wave_cutoff(self, val):
        self.input.incar['ENCUT'] = val

    @property
    def exchange_correlation_functional(self):
        return self.input.potcar["xc"]

    @exchange_correlation_functional.setter
    def exchange_correlation_functional(self, val):
        """

        Args:
            exchange_correlation_functional:

        Returns:

        """
        if val in ["PBE", "pbe", "GGA", "gga"]:
            self.input.potcar["xc"] = "PBE"
        elif val in ["LDA", "lda"]:
            self.input.potcar["xc"] = "LDA"
        else:
            self.input.potcar["xc"] = val

    @property
    def spin_constraints(self):
        if 'I_CONSTRAINED_M' in self.input.incar._dataset['Parameter']:
            return self.input.incar['I_CONSTRAINED_M'] == 1 or self.input.incar['I_CONSTRAINED_M'] == 2
        else:
            return False

    @spin_constraints.setter
    def spin_constraints(self, val):
        self.input.incar['I_CONSTRAINED_M'] = val

    @property
    def write_electrostatic_potential(self):
        return bool(self.input.incar["LVTOT"])

    @write_electrostatic_potential.setter
    def write_electrostatic_potential(self, val):
        self.input.incar["LVTOT"] = bool(val)
        if bool(val):
            self.input.incar["LVHAR"] = True

    @property
    def write_charge_density(self):
        return bool(self.input.incar["LCHARG"])

    @write_charge_density.setter
    def write_charge_density(self, val):
        self.input.incar["LCHARG"] = bool(val)

    @property
    def write_wave_funct(self):
        return self.input.incar['LWAVE']

    @write_wave_funct.setter
    def write_wave_funct(self, write_wave):
        if not isinstance(write_wave, bool):
            raise ValueError('write_wave_funct, can either be True or False.')
        self.input.incar['LWAVE'] = write_wave

    @property
    def write_resolved_dos(self):
        return self.input.incar['LORBIT']

    @write_resolved_dos.setter
    def write_resolved_dos(self, resolved_dos):
        if not isinstance(resolved_dos, bool) and not isinstance(resolved_dos, int):
            raise ValueError('write_resolved_dos, can either be True, False or 0, 1, 2, 5, 10, 11, 12.')
        self.input.incar['LORBIT'] = resolved_dos


    @property
    def sorted_indices(self):
        """
        How the original atom indices are ordered in the vasp format (species by species)
        """
        self._sorted_indices = vasp_sorter(self.structure)
        return self._sorted_indices

    @sorted_indices.setter
    def sorted_indices(self, val):
        """
        Setter for the sorted indices
        """
        self._sorted_indices = val

    # Compatibility functions
    def write_input(self):
        """
        Call routines that generate the INCAR, POTCAR, KPOINTS and POSCAR input files
        """
        if self.input.incar['SYSTEM'] == 'pyiron_jobname':
            self.input.incar['SYSTEM'] = self.job_name
        self.write_magmoms()
        self.set_coulomb_interactions()
        self.input.write(structure=self.structure, directory=self.working_directory)

    # define routines that collect all output files
    def collect_output(self):
        """
        Collects the outputs and stores them to the hdf file
        """
        if self.structure is None or len(self.structure) == 0:
            try:
                self.structure = self.get_final_structure_from_file(filename="CONTCAR")
            except IOError:
                self.structure = self.get_final_structure_from_file(filename="POSCAR")
        self.output.structure = self.structure.copy()
        try:
            self.output.collect(directory=self.working_directory)
        except VaspCollectError:
            self._logger.info("The vasprun file is either corrupted or the simulation crashed")
            self.status.aborted = True
            return
        self.output.to_hdf(self._hdf5)

    def cleanup(self, files_to_remove=("WAVECAR", "CHGCAR", "CHG", "vasprun.xml")):
        """
        Removes excess files (by default: WAVECAR, CHGCAR, CHG)
        """
        list_files = self.list_files()
        for file in list_files:
            if file in files_to_remove:
                abs_file_path = os.path.join(self.working_directory, file)
                os.remove(abs_file_path)

    def collect_logfiles(self):
        """
        Collect errors and warnings.
        """
        self.collect_errors()
        self.collect_warnings()

    def collect_warnings(self):
        """
        Collects warnings from the VASP run
        """
        # TODO: implement for VASP
        self._logger.info("collect_warnings() is not yet implemented for VASP")

    def collect_errors(self):
        """
        Collects errors from the VASP run
        """
        # TODO: implement for vasp
        self._logger.info("collect_errors() is not yet implemented for VASP")

    def from_directory(self, directory):
        """
        The Vasp instance is created by parsing the input and outpus from the specified directory
        Args:
            directory (str): Path to the directory
        """
        if not self.status.finished:
            # _ = s.top_path(directory)
            files = os.listdir(directory)
            vp_new = Vr()
            if "OUTCAR.gz" in files:
                _ = subprocess.check_output(['gzip', '-d', 'OUTCAR.gz'], cwd=directory, shell=False,
                                            universal_newlines=True)
                files = os.listdir(directory)
            if "vasprun.xml.bz2" in files:
                _ = subprocess.check_output(['bzip2', '-d', 'vasprun.xml.bz2'], cwd=directory, shell=False,
                                            universal_newlines=True)
                files = os.listdir(directory)
            try:
                assert ("OUTCAR" in files or "vasprun.xml" in files)
                if "vasprun.xml" in files:
                    vp_new.from_file(filename=posixpath.join(directory, "vasprun.xml"))
                    self.structure = vp_new.get_initial_structure()
            except: # except AssertionError:
                pass
                # raise AssertionError("OUTCAR/vasprun.xml should be present in order to import from directory")
            if "INCAR" in files:
                try:
                    self.input.incar.read_input(posixpath.join(directory, "INCAR"), ignore_trigger="!")
                except (IndexError, TypeError, ValueError):
                    pass
            if "KPOINTS" in files:
                try:
                    self.input.kpoints.read_input(posixpath.join(directory, "KPOINTS"), ignore_trigger="!")
                except (IndexError, TypeError, ValueError):
                    pass
            if "POSCAR" in files and "POTCAR" in files:
                structure = read_atoms(posixpath.join(directory, "POSCAR"), species_from_potcar=True)
            else:
                structure = vp_new.get_initial_structure()
            self.structure = structure
            self._write_chemical_formular_to_database()
            self._import_directory = directory
            self.status.collect = True
            self.to_hdf()
            self.collect_output()
            self.status.finished = True
        else:
            return

    def stop_calculation(self, next_electronic_step=False):
        filename = os.path.join(self.working_directory, 'STOPCAR')
        with open(filename, 'w') as f:
            if not next_electronic_step:
                f.write('LSTOP = .TRUE.\n')
            else:
                f.write('LABORT =.TRUE.\n')

    def to_hdf(self, hdf=None, group_name=None):
        """
        Stores the instance attributes into the hdf5 file
        """
        super(Vasp, self).to_hdf(hdf=hdf, group_name=group_name)
        self._structure_to_hdf()
        self.input.to_hdf(self._hdf5)
        self.output.to_hdf(self._hdf5)

    def from_hdf(self, hdf=None, group_name=None):
        """
        Recreates instance from the hdf5 file
        Args:
            hdf (str): Path to the hdf5 file
            group_name (str): Name of the group which contains the object
        """
        super(Vasp, self).from_hdf(hdf=hdf, group_name=group_name)
        self._structure_from_hdf()
        self.input.from_hdf(self._hdf5)
        if "output" in self.project_hdf5.list_groups() and "structure" in self["output"].list_groups():
                self.output.from_hdf(self._hdf5)

    def reset_output(self):
        self.output = Output()

    def get_final_structure_from_file(self, filename="CONTCAR"):
        """
        Get the final structure of the  simulation
        Args:
            filename (str): Path to the CONTCAR file in VASP

        Returns:
            final_structure: pyiron_atomistics.structure.atoms.Atoms object
        """
        filename = posixpath.join(self.working_directory, filename)
        input_structure = self.structure.copy()
        try:
            output_structure = read_atoms(filename=filename, species_list=input_structure.get_parent_elements())
        except (IndexError, ValueError, IOError):
            s.logger.warning("Unable to read output structure")
            return
        input_structure.cell = output_structure.cell.copy()
        input_structure.positions[self.sorted_indices] = output_structure.positions
        return input_structure

    def write_magmoms(self):
        """
        Write the magnetic moments in INCAR from that assigned to the species
        """
        if any(self.structure.get_initial_magnetic_moments().flatten()):
            final_cmd = '   '.join([' '.join([str(spinmom) for spinmom in spin])
                                    if isinstance(spin, list) or isinstance(spin, np.ndarray) else str(spin)
                                    for spin in self.structure.get_initial_magnetic_moments()])
            s.logger.debug('Magnetic Moments are: {0}'.format(final_cmd))
            if "MAGMOM" not in self.input.incar._dataset['Parameter']:
                self.input.incar["MAGMOM"] = final_cmd
            if "ISPIN" not in self.input.incar._dataset['Parameter']:
                self.input.incar["ISPIN"] = 2
            if any([True if isinstance(spin, list) or isinstance(spin, np.ndarray) else False
                    for spin in self.structure.get_initial_magnetic_moments()]):
                self.input.incar['LNONCOLLINEAR'] = True
                if self.spin_constraints and 'M_CONSTR' not in self.input.incar._dataset['Parameter']:
                    self.input.incar['M_CONSTR'] = final_cmd
                if self.spin_constraints and 'LAMBDA' not in self.input.incar._dataset['Parameter']:
                    raise ValueError('LAMBDA is not specified but it is necessary for non collinear calculations.')
            if self.spin_constraints and not self.input.incar['LNONCOLLINEAR']:
                raise ValueError('Spin constraints are only avilable for non collinear calculations.')
        else:
            s.logger.debug('No magnetic moments')

    def set_coulomb_interactions(self, interaction_type=2, ldau_print=True):
        """
        Write the on-site Coulomb interactions in the INCAR file
        Args:
            interaction_type (int): Type of Coulombic interaction
              1 - Asimov method
              2 - Dudarev method
            ldau_print (boolean): True/False
        """
        obj_lst = self.structure.get_species_objects()
        ldaul = []
        ldauu = []
        ldauj = []
        needed = False
        for el_obj in obj_lst:
            conditions = []
            if isinstance(el_obj.tags, dict):
                for tag in ['ldauu', 'ldaul', 'ldauj']:
                    conditions.append(tag in el_obj.tags.keys())
                if not any(conditions):
                    ldaul.append('-1')
                    ldauu.append('0')
                    ldauj.append('0')
                if any(conditions) and not all(conditions):
                    raise ValueError('All three tags ldauu,ldauj and ldaul have to be specified')
                if all(conditions):
                    needed = True
                    ldaul.append(str(el_obj.tags['ldaul']))
                    ldauu.append(str(el_obj.tags['ldauu']))
                    ldauj.append(str(el_obj.tags['ldauj']))
        if needed:
            self.input.incar["LDAU"] = True
            self.input.incar["LDAUTYPE"] = interaction_type
            self.input.incar["LDAUL"] = ' '.join(ldaul)
            self.input.incar["LDAUU"] = ' '.join(ldauu)
            self.input.incar["LDAUJ"] = ' '.join(ldauj)
            if ldau_print:
                self.input.incar["LDAUPRINT"] = 2
        else:
            s.logger.debug('No on site coulomb interactions')

    def set_algorithm(self, algorithm='Fast', ialgo=None):
        """
        Args:
            algorithm (str): Algorithm defined by VASP (Fast, Normal etc.)
            ialgo (int): Sets the IALGO tag in VASP. If not none, this overwrites algorithm

        """
        algorithm_list = ['Fast', 'Accurate', 'Normal', 'Very Fast']
        if ialgo is not None:
            self.input.incar["IALGO"] = int(ialgo)
        else:
            self.input.incar["ALGO"] = str(algorithm)
            if algorithm not in algorithm_list:
                s.logger.warn(msg="Algorithm {} is unusual for VASP. "
                                  "I hope you know what you are up to".format(algorithm))

    def calc_minimize(self, electronic_steps=60, ionic_steps=100, max_iter=None, pressure=None, algorithm=None,
                      retain_charge_density=False, retain_electrostatic_potential=False, ionic_energy=None,
                      ionic_forces=None, volume_only=False):
        """
        Function to setup the hamiltonian to perform ionic relaxations using DFT. The ISIF tag has to be supplied
        separately.
        Args:
            ionic_energy: 
            ionic_forces: 
            electronic_steps (int): Maximum number of electronic steps
            ionic_steps (int): Maximum number of ionic
            max_iter (int): Maximum number of iterations
            pressure (float): External pressure to be applied
            algorithm (str): Type of VASP algorithm to be used "Fast"/"Accurate"
            retain_charge_density (boolean): True/False
            retain_electrostatic_potential (boolean): True/False
            volume_only (boolean): Option to relax only the volume (keeping the relative coordinates fixed
        """
        super(Vasp, self).calc_minimize(electronic_steps=electronic_steps, ionic_steps=ionic_steps, max_iter=max_iter,
                                        pressure=pressure, algorithm=algorithm,
                                        retain_charge_density=retain_charge_density,
                                        retain_electrostatic_potential=retain_electrostatic_potential,
                                        ionic_energy=ionic_energy, ionic_forces=ionic_forces, volume_only=volume_only)
        if volume_only:
            self.input.incar["ISIF"] = 7
        else:
            if pressure == 0.0:
                self.input.incar["ISIF"] = 3
            else:
                self.input.incar["ISIF"] = 2

        if max_iter:
            electronic_steps = max_iter
            ionic_steps = max_iter

        self.input.incar["IBRION"] = 2
        self.input.incar["NELM"] = electronic_steps
        self.input.incar["NSW"] = ionic_steps
        if algorithm is not None:
            self.set_algorithm(algorithm=algorithm)
        if retain_charge_density:
            self.write_charge_density = retain_charge_density
        if retain_electrostatic_potential:
            self.write_electrostatic_potential = retain_electrostatic_potential
        return

    def calc_static(self, electronic_steps=60, algorithm=None, retain_charge_density=False,
                    retain_electrostatic_potential=False):
        """
        Function to setup the hamiltonian to perform static SCF DFT runs.

        Args:
            electronic_steps (int): Maximum number of electronic steps
            algorithm: Type of VASP algorithm to be used "Fast"/"Accurate"
            retain_charge_density (boolean): True/False
            retain_electrostatic_potential (boolean): True/False
        """
        super(Vasp, self).calc_static(electronic_steps=electronic_steps, algorithm=algorithm,
                                      retain_charge_density=retain_charge_density,
                                      retain_electrostatic_potential=retain_electrostatic_potential)
        self.input.incar["IBRION"] = -1
        self.input.incar["NELM"] = electronic_steps
        if algorithm is not None:
            if algorithm is not None:
                self.set_algorithm(algorithm=algorithm)
        if retain_charge_density:
            self.write_charge_density = retain_charge_density
        if retain_electrostatic_potential:
            self.write_electrostatic_potential = retain_electrostatic_potential

    def calc_md(self, temperature=None, n_ionic_steps=1000, n_print=1, dt=1.0, retain_charge_density=False,
                retain_electrostatic_potential=False, **kwargs):
        """
        Sets appropriate tags for molecular dynamics in VASP
        Args:
            temperature (int/float/list): Temperature/ range of temperatures in Kelvin
            n_ionic_steps (int): Maximum number of ionic steps
            n_print (int): Prints outputs every n_print steps
            dt (float): time step (fs)
            retain_charge_density (boolean): True/False
            retain_electrostatic_potential (boolean): True/False
        """
        super(Vasp, self).calc_md(temperature=temperature, n_ionic_steps=n_ionic_steps, n_print=n_print, dt=dt,
                                  retain_charge_density=retain_charge_density,
                                  retain_electrostatic_potential=retain_electrostatic_potential, **kwargs)
        if temperature is not None:
            # NVT ensemble
            self.input.incar["SMASS"] = 3
            if isinstance(temperature, (int, float)):
                self.input.incar["TEBEG"] = temperature
            else:
                self.input.incar["TEBEG"] = temperature[0]
                self.input.incar["TEEND"] = temperature[-1]
        else:
            # NVE ensemble
            self.input.incar["SMASS"] = -3
        self.input.incar["NSW"] = n_ionic_steps
        self.input.incar["NBLOCK"] = int(n_print)
        self.input.incar["POTIM"] = dt
        if retain_charge_density:
            self.write_charge_density = retain_charge_density
        if retain_electrostatic_potential:
            self.write_electrostatic_potential = retain_electrostatic_potential
        for key in kwargs.keys():
            s.logger.warning("{}tag not relevant for vasp".format(key))

    def set_kpoints(self, mesh=None, scheme='MP', center_shift=None, symmetry_reduction=True, manual_kpoints=None,
                    weights=None, reciprocal=True, kmesh_density=None):
        """
        Function to setup the k-points for the VASP job
        Args:
            mesh (list): Size of the mesh (in the MP scheme)
            scheme (str): Type of k-point generation scheme (MP/GP(gamma point)/Manual/Line)
            center_shift (list): Shifts the center of the mesh from the gamma point by the given vector
            symmetry_reduction (boolean): Tells if the symmetry reduction is to be applied to the k-points
            manual_kpoints (list/numpy.ndarray instance): Manual list of k-points
            weights(list/numpy.ndarray instance): Manually supplied weights to each k-point in case of the manual mode
            reciprocal (boolean): Tells if the supplied values are in reciprocal (direct) or cartesian coordinates (in
            reciprocal space)
            kmesh_density (float):
        """

        if not symmetry_reduction:
            self.input.incar["ISYM"] = -1
        scheme_list = ["MP", "GP", "Line", "Manual"]
        assert (scheme in scheme_list)
        if scheme == "MP":
            if mesh is None:
                if kmesh_density is not None:
                    mesh = self._get_k_mesh_by_cell(self.structure, kmesh_density)
                else:
                    mesh = [4, 4, 4]
            self.input.kpoints.set(size_of_mesh=mesh, shift=center_shift)
        if scheme == "GP":
            self.input.kpoints.set(size_of_mesh=[1, 1, 1], method="Gamma Point")
        if scheme == "Line":
            raise NotImplementedError("The line mode is not implemented as yet")
        if scheme == "Manual":
            if manual_kpoints is None:
                raise ValueError("For the manual mode, the kpoints list should be specified")
            else:
                if weights is not None:
                    assert (len(manual_kpoints) == len(weights))
                self.input.kpoints.set_value(line=1, val=str(len(manual_kpoints)))
                if reciprocal:
                    self.input.kpoints.set_value(line=2, val="Reciprocal")
                else:
                    self.input.kpoints.set_value(line=2, val="Cartesian")
                for i, kpt in enumerate(manual_kpoints):
                    if weights is not None:
                        wt = weights[i]
                    else:
                        wt = 1.0
                    qpt_str = np.array([kpt[0], kpt[1], kpt[2], wt])
                    qpt_str = np.array(qpt_str, dtype=str)
                    qpt_str = [a for a in qpt_str]
                    qpt_str = " ".join(qpt_str)
                    qpt_str = qpt_str.encode("utf8")
                    self.input.kpoints.set_value(line=3 + i, val=qpt_str)

    def set_for_band_structure_calc(self, num_points, structure=None, read_charge_density=True):
        """
        Sets up the input for a non self-consistent bandstructure calculation
        Args:
            num_points (int): Number of k-points along the total BZ path
            structure (pyiron_atomistics.structure.atoms.Atoms instance): Structure for which the bandstructure is to be
                                                                       generated. (default is the input structure)
            read_charge_density (boolean): If True, a charge density from a previous SCF run is used (recommended)

        """
        if read_charge_density:
            self.input.incar["ICHARG"] = 11
        if structure is None:
            assert (self.output.structure is not None)
            structure = self.output.structure
        from pyiron_dft.bandstructure import Bandstructure
        bs_obj = Bandstructure(structure)
        _, q_point_list, [_, _] = bs_obj.get_path(num_points=num_points, path_type="full")
        q_point_list = np.array(q_point_list)
        self.set_kpoints(scheme="Manual", symmetry_reduction=False, manual_kpoints=q_point_list, weights=None,
                         reciprocal=False)

    def get_structure(self, iteration_step=-1):
        """
        Gets the structure from a given iteration step of the simulation (MD/ionic relaxation). For static calculations
        there is only one ionic iteration step
        Args:
            iteration_step (int): Step for which the structure is requested

        Returns:
            pyiron_atomistics.structure.atoms.Atoms object


        """
        assert (self.structure is not None)
        snapshot = self.structure.copy()
        snapshot.cell = self.get("output/generic/cells")[iteration_step]
        snapshot.positions = self.get("output/generic/positions")[iteration_step]
        return snapshot

    def set_convergence_precision(self, ionic_energy=1.E-5, electronic_energy=1.E-7, ionic_forces=None):
        """
        Sets the electronic and ionic convergence precision. For ionic convergence either the energy or the force
        precision is required
        Args:
            ionic_energy (float): Ionic energy convergence precision (eV)
            electronic_energy (float): Electronic energy convergence precision (eV)
            ionic_forces (float): Ionic force convergence precision (eV/A)
        """
        self.input.incar["EDIFF"] = electronic_energy
        if ionic_forces is not None:
            self.input.incar["EDIFFG"] = -1. * abs(ionic_forces)
        else:
            self.input.incar["EDIFFG"] = abs(ionic_energy)

    def set_electric_field(self, e_field=0.1, direction=2, dipol_position=None):
        """
        Set an external electric field using the dipole layer method proposed by [Neugebauer & Scheffler]_
        Args:
            e_field (float): Magnitude of the external electric field (eV/A)
            direction (int): Direction along which the field has to be applied (0, 1, or 2)
            dipol_position (list): Position of the center of the dipole (not the center of the vacuum) in relative
                                coordinates
        .. [Neugebauer & Scheffler] Phys. Rev. B 46, 16067
        """
        assert (direction in range(3))
        self.input.incar["ISYM"] = 0
        self.input.incar["LORBIT"] = 11
        self.input.incar["IDIPOL"] = direction + 1
        self.input.incar["LDIPOL"] = True
        self.input.incar["EFIELD"] = e_field
        if dipol_position is not None:
            self.input.incar["DIPOL"] = " ".join(str(val) for val in dipol_position)

    def set_occupancy_smearing(self, smearing="fermi", width=0.1, ismear=None):
        """
        Set how the finite temperature smearing is applied in determining partial occupancies
        Args:
            smearing (str): Type of smearing (fermi/gaussian etc.)
            width (float): Smearing width (eV)
            ismear (int): Directly sets the ISMEAR tag. Overwrites the smearing tag
        """
        ismear_dict = {"fermi": -1, "gaussian": 0, "MP": 1}
        if ismear is not None:
            self.input.incar["ISMEAR"] = int(ismear)
        else:
            self.input.incar["ISMEAR"] = ismear_dict[smearing]
        self.input.incar["SIGMA"] = width

    def set_fft_mesh(self, nx=None, ny=None, nz=None):
        """
        Set the number of points in the respective directions for the 3D FFT mesh used for computing the charge density
        or electrostatic potentials. In VASP, using PAW potentials, this refers to the "finer fft mesh". If no values
        are set, the default settings from Vasp are used to set the number of grid points.
        Args:
            nx (int): Number of points on the x-grid
            ny (int): Number of points on the y-grid
            nz (int): Number of points on the z-grid
        """
        if nx is not None:
            self.input.incar["NGXF"] = int(nx)
        if ny is not None:
            self.input.incar["NGYF"] = int(ny)
        if nz is not None:
            self.input.incar["NGZF"] = int(nz)

    def get_electronic_structure(self):
        """
        Gets the electronic structure instance from the hdf5 file

        Returns:
                pyiron.pyiron_atomistics.waves.electronic.ElectronicStructure instance
        """
        if not self.status.finished:
            return
        else:
            with self.project_hdf5.open("output") as ho:
                es_obj = ElectronicStructure()
                es_obj.from_hdf(ho)
            return es_obj

    def get_charge_density(self):
        """
        Gets the charge density from the hdf5 file. This value is normalized by the volume

        Returns:
                pyiron_atomistics.volumetric.generic.VolumetricData instance
        """
        if not self.status.finished:
            return
        else:
            with self.project_hdf5.open("output") as ho:
                cd_obj = VaspVolumetricData()
                cd_obj.from_hdf(ho, "charge_density")
            return cd_obj

    def get_electrostatic_potential(self):
        """
        Gets the electrostatic potential from the hdf5 file.

        Returns:
                pyiron_atomistics.volumetric.generic.VolumetricData instance
        """
        if not self.status.finished:
            return
        else:
            with self.project_hdf5.open("output") as ho:
                es_obj = VaspVolumetricData()
                es_obj.from_hdf(ho, "electrostatic_potential")
            return es_obj

    def restart(self, snapshot=-1, job_name=None, job_type=None):
        """
        Restart a new job created from an existing Vasp calculation.
        Args:
            snapshot (int): Snapshot of the calculations which would be the initial structure of the new job
            job_name (str): Job name
            job_type (str): Job type. If not specified a Vasp job type is assumed

        Returns:
            new_ham (pyiron_vasp.vasp.Vasp instance): New job
        """
        new_ham = super(Vasp, self).restart(snapshot=snapshot, job_name=job_name, job_type=job_type)
        if new_ham.__name__ == self.__name__:
            new_ham.input.potcar["xc"] = self.input.potcar["xc"]
        return new_ham

    def restart_from_charge_density(self, snapshot=-1, job_name=None, job_type=None, icharg=None,
                                    self_consistent_calc=False):
        """
        Restart a new job created from an existing Vasp calculation by reading the charge density.
        Args:
            snapshot (int): Snapshot of the calculations which would be the initial structure of the new job
            job_name (str): Job name
            job_type (str): Job type. If not specified a Vasp job type is assumed
            icharg (int): Vasp ICHARG tag
            self_consistent_calc (boolean): Tells if the new calculation is self consistent

        Returns:
            new_ham (pyiron_vasp.vasp.Vasp instance): New job
        """
        new_ham = self.restart(snapshot=snapshot, job_name=job_name, job_type=job_type)
        if new_ham.__name__ == self.__name__:
            try:
                new_ham.restart_file_list.append(posixpath.join(self.working_directory, "CHGCAR"))
            except IOError:
                self.logger.warn(msg="A CHGCAR from job: {} is not generated and therefore it can't be read.".
                                 format(self.job_name))
            if icharg is None:
                new_ham.input.incar["ICHARG"] = 1
                if not self_consistent_calc:
                    new_ham.input.incar["ICHARG"] = 11
            else:
                new_ham.input.incar["ICHARG"] = icharg
        return new_ham

    def restart_from_wave_functions(self, snapshot=-1, job_name=None, job_type=None, istart=1):

        """
        Restart a new job created from an existing Vasp calculation by reading the wave functions.
        Args:
            snapshot (int): Snapshot of the calculations which would be the initial structure of the new job
            job_name (str): Job name
            job_type (str): Job type. If not specified a Vasp job type is assumed
            istart (int): Vasp ISTART tag

        Returns:
            new_ham (pyiron_vasp.vasp.Vasp instance): New job
        """
        new_ham = self.restart(snapshot=snapshot, job_name=job_name, job_type=job_type)
        if new_ham.__name__ == self.__name__:
            try:
                new_ham.restart_file_list.append(posixpath.join(self.working_directory, "WAVECAR"))
            except IOError:
                self.logger.warn(msg="A WAVECAR from job: {} is not generated and therefore it can't be read.".
                                 format(self.job_name))
            new_ham.input.incar["ISTART"] = istart
        return new_ham

    def copy_chgcar(self, old_vasp_job):
        """
        Copy CHGCAR from previous VASP calcualtion to the new VASP job.
        Sets ICHARG = 1
        :param old_vasp_job: finished VASP hamiltonian
        :return:
        """
        self.copy_file(old_vasp_job)
        self.input.incar["ICHARG"] = 1

    def copy_wavecar(self, old_vasp_job):
        """
        Copy WAVECAR from previous VASP calcualtion to the new VASP job.
        Sets ISTART = 1
        :param old_vasp_job: finished VASP hamiltonian
        :return:
        """
        self.copy_file(old_vasp_job, filename="WAVECAR")
        self.input.incar["ISTART"] = 1

    def copy_file(self, old_vasp_job, filename="CHGCAR"):
        if not isinstance(old_vasp_job, Vasp):
            raise ValueError("old_vasp_job is not Vasp job type")
        import os
        old_path = os.path.join(old_vasp_job.working_directory, filename)
        new_path = os.path.join(self.working_directory, filename)
        from shutil import copyfile
        if not os.path.isdir(self.working_directory):
            os.makedirs(self.working_directory)
        copyfile(old_path, new_path)

    def set_spin_constraint(self, direction=False, norm=False):
        assert isinstance(direction, bool)
        assert isinstance(norm, bool)
        if direction and norm:
            self.input.incar['I_CONSTRAINED_M'] = 2
        elif direction:
            self.input.incar['I_CONSTRAINED_M'] = 1

    def __del__(self):
        pass


class Input:
    """
    Handles setting the input parameters for a VASP job.

    Attributes:

        incar: .pyiron_vasp.vasp.Incar instance to handle the INCAR file inputs in VASP
        kpoints: pyiron_vasp.vasp.Kpoints instance to handle the KPOINTS file inputs in VASP
        potcar: pyiron_vasp.vasp.Potcar instance to set the appropriate POTCAR files for the simulation

    Ideally, the user would not have to access the Input instance unless the user wants to set an extremely specific
    VASP tag which can't se set using functions in Vasp().

    Examples:

        >>> atoms =  CrystalStructure("Pt", BravaisBasis="fcc", a=3.98)
        >>> ham = Vasp("trial")
        >>> ham.structure = atoms
        >>> ham.calc_static()
        >>> assert(atoms==ham.structure)
        >>> assert(ham.input.incar["ISIF"]==-1)
    """

    def __init__(self):
        self.incar = Incar(table_name="incar")
        self.kpoints = Kpoints(table_name="kpoints")
        self.potcar = Potcar(table_name="potcar")

    def write(self, structure, directory=None):
        """
        Writes all the input files to a specified directory

        Args:
            structure (pyiron_atomistics.structure.atoms.Atoms instance): Structure to be written
            directory (str): The working directory for the VASP run
        """
        self.incar.write_file(file_name="INCAR", cwd=directory)
        self.kpoints.write_file(file_name="KPOINTS", cwd=directory)
        self.potcar.potcar_set_structure(structure)
        self.potcar.write_file(file_name="POTCAR", cwd=directory)
        # Write the species info in the POSCAR file only if there are no user defined species
        is_user_defined = list()
        for species in structure.get_species_objects():
            is_user_defined.append(species.Parent is not None)
        do_not_write_species = any(is_user_defined)
        write_poscar(structure, filename=posixpath.join(directory, "POSCAR"),
                     write_species=not do_not_write_species)

    def to_hdf(self, hdf):
        """
        Writes the important attributes to a hdf file

        Args:
            hdf: The hdf5 instance
        """

        with hdf.open("input") as hdf5_input:
            self.incar.to_hdf(hdf5_input)
            self.kpoints.to_hdf(hdf5_input)
            self.potcar.to_hdf(hdf5_input)

    def from_hdf(self, hdf):
        """
        Reads the attributes and reconstructs the object from a hdf file
        Args:
            hdf: The hdf5 instance
        """
        with hdf.open("input") as hdf5_input:
            self.incar.from_hdf(hdf5_input)
            self.kpoints.from_hdf(hdf5_input)
            self.potcar.from_hdf(hdf5_input)


class Output:
    """
    Handles the output from a VASP simulation.

    Attributes:

        electronic_structure: Gives the electronic structure of the system

        electrostatic_potential: Gives the electrostatic/local potential of the system

        charge_density: Gives the charge density of the system
    """

    def __init__(self):
        self._structure = None
        self.outcar = Outcar()
        self.generic_output = GenericOutput()
        self.dft_output = DFTOutput()
        self.description = "This contains all the output static from this particular vasp run"
        self.charge_density = VaspVolumetricData()
        self.electrostatic_potential = VaspVolumetricData()
        self.procar = Procar()
        self.electronic_structure = ElectronicStructure()
        self.vp_new = Vr()

    @property
    def structure(self):
        """
        Getter for the output structure
        """
        return self._structure

    @structure.setter
    def structure(self, atoms):
        """
        Setter for the output structure
        """
        self._structure = atoms

    def collect(self, directory=os.getcwd()):
        """
        Collects output from the working directory
        Args:
            directory (str): Path to the directory
        """
        sorted_indices = vasp_sorter(self.structure)
        files_present = os.listdir(directory)
        read_only_from_outcar = False
        if "OUTCAR" in files_present:
            self.outcar.from_file(filename=posixpath.join(directory, "OUTCAR"))
        if "vasprun.xml" in files_present:
            try:
                self.vp_new.from_file(filename=posixpath.join(directory, "vasprun.xml"))
            except VasprunError:
                # raise VaspCollectError("The vasprun file is either corrupted or the simulation crashed")
                read_only_from_outcar = True
            if not read_only_from_outcar:
                log_dict = dict()
                log_dict["forces"] = self.vp_new.vasprun_dict["forces"]
                log_dict["cells"] = self.vp_new.vasprun_dict["cells"]
                log_dict["volume"] = [np.linalg.det(cell) for cell in self.vp_new.vasprun_dict["cells"]]
                # log_dict["total_energies"] = self.vp_new.vasprun_dict["total_energies"]
                log_dict["energy_tot"] = self.vp_new.vasprun_dict["total_energies"]
                if "kinetic_energies" in self.vp_new.vasprun_dict.keys():
                    log_dict["energy_pot"] = log_dict["energy_tot"] - self.vp_new.vasprun_dict["kinetic_energies"]
                else:
                    log_dict["energy_pot"] = log_dict["energy_tot"]
                log_dict["steps"] = np.arange(len(log_dict["energy_tot"]))
                log_dict["positions"] = self.vp_new.vasprun_dict["positions"]
                log_dict["forces"][:, sorted_indices] = log_dict["forces"].copy()
                log_dict["positions"][:, sorted_indices] = log_dict["positions"].copy()
                log_dict["temperatures"] = self.outcar.parse_dict["temperatures"]
                log_dict["pressures"] = self.outcar.parse_dict["pressures"]
                log_dict["unwrapped_positions"] = unwrap_coordinates(positions=log_dict["positions"], cell=None,
                                                                     is_relative=True)
                for i, pos in enumerate(log_dict["positions"]):
                    log_dict["positions"][i] = np.dot(pos, log_dict["cells"][i])
                    log_dict["unwrapped_positions"][i] = np.dot(log_dict["unwrapped_positions"][i].copy(),
                                                                log_dict["cells"][i])
                # log_dict["scf_energies"] = self.vp_new.vasprun_dict["scf_energies"]
                # log_dict["scf_dipole_moments"] = self.vp_new.vasprun_dict["scf_dipole_moments"]
                self.electronic_structure = self.vp_new.get_electronic_structure()
                if self.electronic_structure.grand_dos_matrix is not None:
                    self.electronic_structure.grand_dos_matrix[:, :, :, sorted_indices, :] = \
                        self.electronic_structure.grand_dos_matrix[:, :, :, :, :].copy()
                if self.electronic_structure.resolved_densities is not None:
                    self.electronic_structure.resolved_densities[:, sorted_indices, :, :] = \
                        self.electronic_structure.resolved_densities[:, :, :, :].copy()
                self.structure.positions = log_dict["positions"][-1]
                self.structure.cell = log_dict["cells"][-1]

        elif ("vasprun.xml" not in files_present) or read_only_from_outcar:
            assert ("OUTCAR" in files_present)
            log_dict = self.outcar.parse_dict.copy()
            log_dict["energy_tot"] = log_dict["energies"].copy()
            if len(log_dict["magnetization"]) == len(sorted_indices):
                magnetization = np.array(log_dict["magnetization"]).copy()
                final_magmoms = np.array(log_dict["final_magmoms"]).copy()
                magnetization[sorted_indices] = magnetization.copy()
                final_magmoms[sorted_indices] = final_magmoms.copy()
                log_dict["magnetization"] = magnetization.to_list()
                log_dict["final_magmoms"] = final_magmoms.to_list()
            del log_dict["fermi_level"]
            if "PROCAR" in files_present:
                try:
                    self.electronic_structure = self.procar.from_file(filename=posixpath.join(directory, "PROCAR"))
                    #  Even the atom resolved values have to be sorted from the vasp atoms order to the Atoms order
                    self.electronic_structure.grand_dos_matrix[:, :, :, sorted_indices, :] = \
                        self.electronic_structure.grand_dos_matrix[:, :, :, :, :].copy()
                    try:
                        self.electronic_structure.efermi = self.outcar.parse_dict["fermi_level"]
                    except KeyError:
                        self.electronic_structure.efermi = self.vp_new.vasprun_dict["efermi"]
                except ValueError:
                    pass
        else:
            raise VaspCollectError("Not able to parse vasprun.xml or OUTCAR")
        # important that we "reverse sort" the atoms in the vasp format into the atoms in the atoms class
        self.generic_output.log_dict = log_dict
        if "vasprun.xml" in files_present and not read_only_from_outcar:
            self.dft_output.log_dict["parameters"] = self.vp_new.vasprun_dict["parameters"]
            self.dft_output.log_dict["scf_energies"] = self.vp_new.vasprun_dict["scf_energies"]
            self.dft_output.log_dict["scf_fr_energies"] = self.vp_new.vasprun_dict["scf_fr_energies"]
            self.dft_output.log_dict["scf_0_energies"] = self.vp_new.vasprun_dict["scf_0_energies"]
            self.dft_output.log_dict["scf_dipole_moments"] = self.vp_new.vasprun_dict["scf_dipole_moments"]
            total_dipole_moments = list()
            if len(self.dft_output.log_dict["scf_dipole_moments"][0]) > 0:
                for dip in self.dft_output.log_dict["scf_dipole_moments"]:
                    total_dipole_moments.append(np.array(dip[-1]))

            total_dipole_moments = np.array(total_dipole_moments)
            self.dft_output.log_dict["total_dipole_moments"] = total_dipole_moments
            self.dft_output.log_dict["total_energies"] = self.vp_new.vasprun_dict["total_energies"]
            self.dft_output.log_dict["total_fr_energies"] = self.vp_new.vasprun_dict["total_fr_energies"]
            self.dft_output.log_dict["total_0_energies"] = self.vp_new.vasprun_dict["total_0_energies"]
            if "kinetic_energies" in self.vp_new.vasprun_dict.keys():
                self.dft_output.log_dict["kinetic_energies"] = self.vp_new.vasprun_dict["kinetic_energies"]
        if "LOCPOT" in files_present:
            self.electrostatic_potential.from_file(filename=posixpath.join(directory, "LOCPOT"), normalize=False)
        if "CHGCAR" in files_present:
            self.charge_density.from_file(filename=posixpath.join(directory, "CHGCAR"), normalize=True)
        if read_only_from_outcar:
            raise VaspCollectError("The vasprun file is either corrupted or the simulation crashed")

    def to_hdf(self, hdf):
        """
        Writes the important attributes to a hdf file

        Args:
            hdf: The hdf5 instance
        """
        with hdf.open("output") as hdf5_output:
            hdf5_output["description"] = self.description
            self.generic_output.to_hdf(hdf5_output)
            self.dft_output.to_hdf(hdf5_output)
            try:
                self.structure.to_hdf(hdf5_output)
            except AttributeError:
                pass

            # with hdf5_output.open("vasprun") as hvr:
            #  if self.vasprun.dict_vasprun is not None:
            #     for key, val in self.vasprun.dict_vasprun.items():
            #        hvr[key] = val

            if self.electrostatic_potential.total_data is not None:
                self.electrostatic_potential.to_hdf(hdf5_output, group_name="electrostatic_potential")

            if self.charge_density.total_data is not None:
                self.charge_density.to_hdf(hdf5_output, group_name="charge_density")

            if len(self.electronic_structure.kpoint_list) > 0:
                self.electronic_structure.to_hdf(hdf=hdf5_output, group_name="electronic_structure")

            if self.outcar.parse_dict:
                self.outcar.to_hdf(hdf=hdf5_output, group_name="outcar")

    def from_hdf(self, hdf):
        """
        Reads the attributes and reconstructs the object from a hdf file
        Args:
            hdf: The hdf5 instance
        """
        with hdf.open("output") as hdf5_output:
            # self.description = hdf5_output["description"]
            if self.structure is None:
                self.structure = Atoms()
            self.structure.from_hdf(hdf5_output)
            self.generic_output.from_hdf(hdf5_output)
            self.dft_output.from_hdf(hdf5_output)
            try:
                if "electrostatic_potential" in hdf5_output.list_groups():
                    self.electrostatic_potential.from_hdf(hdf5_output, group_name="electrostatic_potential")
                if "charge_density" in hdf5_output.list_groups():
                    self.charge_density.from_hdf(hdf5_output, group_name="charge_density")
                if "electronic_structure" in hdf5_output.list_groups():
                    self.electronic_structure.from_hdf(hdf=hdf5_output)
                if "outcar" in hdf5_output.list_groups():
                    self.outcar.from_hdf(hdf=hdf5_output, group_name="outcar")
            except (TypeError, IOError, ValueError):
                s.logger.warning("Routine from_hdf() not completely successful")


class GenericOutput:
    """
    This class stores the generic output like different structures, energies and forces from a simulation in a highly
    generic format. Usually the user does not have to access this class.

    Attributes:
        log_dict (dict): A dictionary of all tags and values of generic data (positions, forces, etc)
    """

    def __init__(self):
        self.log_dict = dict()
        self.description = "generic_output contains generic output static"

    def to_hdf(self, hdf):
        """
        Writes the important attributes to a hdf file

        Args:
            hdf: The hdf5 instance
        """
        with hdf.open("generic") as hdf_go:
            # hdf_go["description"] = self.description
            for key, val in self.log_dict.items():
                hdf_go[key] = val

    def from_hdf(self, hdf):
        """
        Reads the attributes and reconstructs the object from a hdf file
        Args:
            hdf: The hdf5 instance
        """
        with hdf.open("generic") as hdf_go:
            for node in hdf_go.list_nodes():
                if node == "description":
                    # self.description = hdf_go[node]
                    pass
                else:
                    self.log_dict[node] = hdf_go[node]


class DFTOutput:
    """
    This class stores the DFT specific output

    Attributes:
        log_dict (dict): A dictionary of all tags and values of DFT data
    """

    def __init__(self):
        self.log_dict = dict()
        self.description = "contains DFT specific output"

    def to_hdf(self, hdf):
        """
        Writes the important attributes to a hdf file

        Args:
            hdf: The hdf5 instance
        """
        with hdf.open("dft") as hdf_dft:
            # hdf_go["description"] = self.description
            for key, val in self.log_dict.items():
                hdf_dft[key] = val

    def from_hdf(self, hdf):
        """
        Reads the attributes and reconstructs the object from a hdf file
        Args:
            hdf: The hdf5 instance
        """
        with hdf.open("dft") as hdf_dft:
            for node in hdf_dft.list_nodes():
                if node == "description":
                    # self.description = hdf_go[node]
                    pass
                else:
                    self.log_dict[node] = hdf_dft[node]


class Incar(GenericParameters):
    """
    Class to control the INCAR file of a vasp simulation
    """

    def __init__(self, input_file_name=None, table_name="incar"):
        super(Incar, self).__init__(input_file_name=input_file_name, table_name=table_name, comment_char="#",
                                    separator_char="=")
        self._bool_dict = {True: ".TRUE.", False: ".FALSE."}

    def load_default(self):
        """
        Loads the default file content
        """
        file_content = '''\
SYSTEM =  ToDo  # jobname
PREC = Accurate
ALGO = Fast
ENCUT = 250
LREAL = False
LWAVE = False
LORBIT = 0
'''
        self.load_string(file_content)


class Kpoints(GenericParameters):
    """
    Class to control the KPOINTS file of a vasp simulation
    """

    def __init__(self, input_file_name=None, table_name="kpoints"):
        super(Kpoints, self).__init__(input_file_name=input_file_name, table_name=table_name, val_only=True,
                                      comment_char="!")

    def set(self, method=None, size_of_mesh=None, shift=None):
        """
        Sets appropriate tags and values in the KPOINTS file
        Args:
            method (str): Type of meshing scheme (Gamma Point, MP, Manual or Line)
            size_of_mesh (list/numpy.ndarray): List of size 1x3 specifying the required mesh size
            shift (list): List of size 1x3 specifying the user defined shift from the Gamma point
        """
        if method is not None:
            self.set_value(line=2, val=method)
        if size_of_mesh is not None:
            val = " ".join([str(i) for i in size_of_mesh])
            self.set_value(line=3, val=val)
        if shift is not None:
            val = " ".join([str(i) for i in shift])
            self.set_value(line=4, val=val)

    def load_default(self):
        """
        Loads the default file content
        """
        file_content = '''\
Kpoints file generated with pyCMW
0
Monkhorst_Pack
4 4 4
0 0 0
'''
        self.load_string(file_content)

    def set_kmesh_by_density(self, structure):
        if "density_of_mesh" in self._dataset and self._dataset["density_of_mesh"] is not None:
            if self._dataset["density_of_mesh"] != 0.0:
                k_mesh = get_k_mesh_by_cell(structure.get_cell(),
                                            kspace_per_in_ang=self._dataset["density_of_mesh"])
                self.set(size_of_mesh=k_mesh)


class Potcar(GenericParameters):
    pot_path_dict = {"GGA": "paw-gga-pbe", "PBE": "paw-gga-pbe", "LDA": "paw-lda"}

    def __init__(self, input_file_name=None, table_name="potcar"):
        GenericParameters.__init__(self, input_file_name=input_file_name, table_name=table_name, val_only=False,
                                   comment_char="#")
        self._structure = None
        self.electrons_per_atom_lst = list()
        self.max_cutoff_lst = list()

    def potcar_set_structure(self, structure):
        self._structure = structure
        self._set_potential_paths()

    def modify(self, **modify):
        if "xc" in modify:
            xc_type = modify['xc']
            if xc_type not in self.pot_path_dict:
                raise ValueError("xc type not implemented: " + xc_type)
        GenericParameters.modify(self, **modify)
        if self._structure is not None:
            self._set_potential_paths()

    def _set_potential_paths(self):
        element_list = self._structure.get_species_symbols()  # .ElementList.getSpecies()
        object_list = self._structure.get_species_objects()
        s.logger.debug("element list: {0}".format(element_list))
        self.el_path_lst = []
        try:
            xc = self.get("xc")
        except tables.exceptions.NoSuchNodeError:
            xc = self.get("xc")
        s.logger.debug("XC: {0}".format(xc))
        vasp_potentials = VaspPotentialFile(xc=xc)
        for i, el_obj in enumerate(object_list):
            if isinstance(el_obj.Parent, str):
                el = el_obj.Parent
            else:
                el = el_obj.Abbreviation
            if isinstance(el_obj.tags, dict):
                if 'pseudo_potcar_file' in el_obj.tags.keys():
                    file_name = el_obj.tags['pseudo_potcar_file']
                    el_path = self._find_potential_file(xc=xc, file_name=file_name)
                    if not (os.path.isfile(el_path)):
                        raise ValueError('such a file does not exist in the pp directory')
                else:
                    el_path = self._find_potential_file(path=vasp_potentials.find_default(el)['Filename'].values[0][0])

            else:
                el_path = self._find_potential_file(path=vasp_potentials.find_default(el)['Filename'].values[0][0])

            assert (os.path.isfile(el_path))
            pot_name = "pot_" + str(i)

            if pot_name in self._dataset["Parameter"]:
                try:
                    ind = self._dataset["Parameter"].index(pot_name)
                except (ValueError, IndexError):
                    indices = np.core.defchararray.find(self._dataset["Parameter"], pot_name)
                    ind = np.where(indices == 0)[0][0]
                self._dataset["Value"][ind] = el_path
                self._dataset["Comment"][ind] = ""
            else:
                self._dataset["Parameter"].append("pot_" + str(i))
                self._dataset["Value"].append(el_path)
                self._dataset["Comment"].append("")
            self.el_path_lst.append(el_path)

    def _find_potential_file(self, file_name=None, xc=None, path=None):
        if path is not None:
            for resource_path in s.resource_paths:
                if os.path.exists(os.path.join(resource_path, 'pyiron_vasp', 'potentials', path)):
                    return os.path.join(resource_path, 'pyiron_vasp', 'potentials', path)
        elif xc is not None and file_name is not None:
            for resource_path in s.resource_paths:
                if os.path.exists(os.path.join(resource_path, 'pyiron_vasp', 'potentials', self.pot_path_dict[xc])):
                    resource_path = os.path.join(resource_path, 'pyiron_vasp', 'potentials', self.pot_path_dict[xc])
                if 'potentials' in resource_path:
                    for path, folder_lst, file_lst in os.walk(resource_path):
                        if file_name in file_lst:
                            return os.path.join(path, file_name)
        # Backwards compatibility to the old version
        if path is not None:
            return os.path.join(s.path_potentials, 'vasp', path)
        elif xc is not None and file_name is not None:
            return os.path.join(s.path_potentials, 'vasp', self.pot_path_dict[xc], file_name)
        else:
            raise ValueError('Either the filename or the functional has to be defined.')

    def write_file(self, file_name, cwd=None):
        """

        Args:
            file_name:
            cwd:

        Returns:

        """
        self.electrons_per_atom_lst = list()
        self.max_cutoff_lst = list()
        self._set_potential_paths()
        if cwd is not None:
            file_name = posixpath.join(cwd, file_name)
        f = open(file_name, 'w')
        for el_file in self.el_path_lst:
            with open(el_file) as pot_file:
                for i, line in enumerate(pot_file):
                    f.write(line)
                    if i == 1:
                        self.electrons_per_atom_lst.append(int(float(line)))
                    elif i == 14:
                        mystr = line.split()[2][:-1]
                        self.max_cutoff_lst.append(float(mystr))
        f.close()

    def load_default(self):
        file_content = '''\
xc  GGA  # LDA, GGA
'''
        self.load_string(file_content)


def get_k_mesh_by_cell(cell, kspace_per_in_ang=0.10):
    """

    Args:
        cell:
        kspace_per_in_ang:

    Returns:

    """
    latlens = [np.linalg.norm(lat) for lat in cell]
    kmesh = np.ceil(np.array([2*np.pi/ll for ll in latlens]) / kspace_per_in_ang)
    kmesh[kmesh < 1] = 1
    return kmesh


class VaspCollectError(ValueError):
    pass
