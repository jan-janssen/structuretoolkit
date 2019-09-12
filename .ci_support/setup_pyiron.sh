#!/bin/bash
conda install -y -c conda-forge python=${1} ase=3.18 coveralls coverage defusedxml=0.5.0 dill=0.3.0 future=0.17.1 h5io=0.1.1 h5py=2.10.0 matplotlib=3.1.1 mendeleev=0.5.1 numpy=1.17.2 pandas=0.25.1 pathlib2=2.3.4 phonopy=2.3.2 psutil=5.6.3 pysqa=0.0.4 scipy=1.3.1 six==1.12.0 spglib=1.14.1 sqlalchemy=1.3.8 pytables=3.5.2 tqdm=4.35.0
pip install --pre .
