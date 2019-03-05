#!/bin/bash

if [ "$TRAVIS_BRANCH" = "master" ]; then
    # install
    conda install -y -c conda-forge sphinx nbsphinx ipywidgets sphinx_rtd_theme pylint Graphviz # ovito

    git config --global user.email "${GH_EMAIL}"
    git config --global user.name "${GH_USER}"

    cd ..
    mkdir pyiron.github.io
    cd pyiron.github.io
    touch .nojekyll
    echo -e "# Build Status\n\nThis repository is automatically updated based on the changes in https://github.com/pyiron/pyiron .\n[![Build Status](https://travis-ci.org/pyiron/pyiron.svg?branch=master)](https://travis-ci.org/pyiron/pyiron)" > README.md
    cd ..

    cd pyiron
    sphinx-apidoc -f -o docs/apidoc pyiron
    cd docs
    cp -r ../notebooks source
    sphinx-build -b html ./ ../../pyiron.github.io
    cd ..

    mkdir uml
    cd uml
    pyreverse -p pyiron -o png ../pyiron
    cp *.png ../../pyiron.github.io
    cd ..
fi;
